import pytest
import os
import shutil
import subprocess
from app.git.service import GitService, GitError


@pytest.fixture
def git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    ws_root = tmp_path / "worktrees"
    ws_root.mkdir()

    # Initialize a clean git repository
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)

    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    git_service = GitService(workspace_root=str(ws_root))

    return {
        "repo_dir": str(repo_dir),
        "ws_root": str(ws_root),
        "service": git_service,
    }


@pytest.mark.asyncio
async def test_create_worktree_fresh(git_repo):
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    wt_path = await svc.create_worktree(repo_dir, "task-100", "main")
    assert os.path.exists(wt_path)
    assert os.path.exists(os.path.join(wt_path, "README.md"))

    # Verify branch is task/task-100
    branch = await svc.get_current_branch(wt_path)
    assert branch == "task/task-100"


@pytest.mark.asyncio
async def test_create_worktree_idempotent_existing_branch(git_repo):
    """When a task branch already exists (e.g. on retry), create_worktree resets it cleanly without error."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    # First creation
    wt1 = await svc.create_worktree(repo_dir, "task-retry", "main")
    assert os.path.exists(wt1)

    # Second creation (retry scenario with same task_id)
    wt2 = await svc.create_worktree(repo_dir, "task-retry", "main")
    assert os.path.exists(wt2)
    assert wt1 == wt2
    assert await svc.get_current_branch(wt2) == "task/task-retry"


@pytest.mark.asyncio
async def test_create_worktree_disk_deleted_metadata_intact(git_repo):
    """If disk directory was removed without git worktree remove, create_worktree recovers via pruning."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    wt = await svc.create_worktree(repo_dir, "task-desync", "main")
    assert os.path.exists(wt)

    # Simulate rogue disk deletion leaving git metadata dirty
    shutil.rmtree(wt)
    assert not os.path.exists(wt)

    # Calling create_worktree again must succeed cleanly
    wt_recovered = await svc.create_worktree(repo_dir, "task-desync", "main")
    assert os.path.exists(wt_recovered)
    assert await svc.get_current_branch(wt_recovered) == "task/task-desync"


@pytest.mark.asyncio
async def test_create_worktree_preserves_other_worktrees(git_repo):
    """Creating or removing a task worktree must never alter unrelated worktrees."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]
    tmp_parent = os.path.dirname(repo_dir)

    # Create an independent manual worktree simulating user's ForgeFlow-test-worktree
    manual_wt = os.path.join(tmp_parent, "manual-worktree")
    subprocess.run(
        ["git", "worktree", "add", "-b", "manual-branch", manual_wt, "main"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    assert os.path.exists(manual_wt)

    # Create task worktree
    task_wt = await svc.create_worktree(repo_dir, "task-isolated", "main")
    assert os.path.exists(task_wt)
    assert os.path.exists(manual_wt)

    # Remove task worktree
    await svc.remove_worktree(repo_dir, task_wt)
    assert not os.path.exists(task_wt)
    assert os.path.exists(manual_wt)  # User's manual worktree remains untouched!

    # Clean up manual worktree
    subprocess.run(["git", "worktree", "remove", "--force", manual_wt], cwd=repo_dir, capture_output=True)


@pytest.mark.asyncio
async def test_create_worktree_invalid_repo(git_repo):
    svc: GitService = git_repo["service"]
    with pytest.raises(GitError, match="Not a git repository"):
        await svc.create_worktree("C:/non_existent_dir_12345", "task-fail", "main")


@pytest.mark.asyncio
async def test_create_worktree_preserves_existing_commits(git_repo):
    """When a task branch has existing commits, re-attaching a worktree must preserve them."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    # 1. Create worktree
    wt = await svc.create_worktree(repo_dir, "task-preserve", "main")
    assert os.path.exists(wt)

    # 2. Add an intermediate commit on the task branch
    feature_file = os.path.join(wt, "feature.txt")
    with open(feature_file, "w", encoding="utf-8") as f:
        f.write("Important intermediate work\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "WIP: preserve me"], cwd=wt, check=True)

    # 3. Remove worktree (simulating stop/fail)
    await svc.remove_worktree(repo_dir, wt)
    assert not os.path.exists(wt)

    # 4. Re-create worktree with reset_branch=False (default)
    wt_resumed = await svc.create_worktree(repo_dir, "task-preserve", "main", reset_branch=False)
    assert os.path.exists(wt_resumed)

    # 5. Verify the commit was NOT destroyed!
    assert os.path.exists(os.path.join(wt_resumed, "feature.txt"))
    with open(os.path.join(wt_resumed, "feature.txt"), "r", encoding="utf-8") as f:
        assert f.read().strip() == "Important intermediate work"


@pytest.mark.asyncio
async def test_create_worktree_explicit_reset_creates_backup(git_repo):
    """When reset_branch=True is explicitly passed and unique commits exist, a backup ref is created before reset."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    # 1. Create worktree and commit
    wt = await svc.create_worktree(repo_dir, "task-reset", "main")
    feature_file = os.path.join(wt, "file_to_reset.txt")
    with open(feature_file, "w", encoding="utf-8") as f:
        f.write("Work before reset\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "Before reset"], cwd=wt, check=True)

    # 2. Re-create with reset_branch=True
    wt_reset = await svc.create_worktree(repo_dir, "task-reset", "main", reset_branch=True)
    assert os.path.exists(wt_reset)

    # 3. Verify the file is reset (not on active branch)
    assert not os.path.exists(os.path.join(wt_reset, "file_to_reset.txt"))

    # 4. Verify a backup ref exists under refs/forgeflow/backups/
    res = subprocess.run(
        ["git", "for-each-ref", "refs/forgeflow/backups/", "--format=%(refname)"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True
    )
    assert "refs/forgeflow/backups/task_task-reset_" in res.stdout


@pytest.mark.asyncio
async def test_task_id_path_traversal_rejection(git_repo):
    """Malicious task IDs attempting path traversal outside workspace root are rejected."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    dangerous_ids = [
        "../../escape",
        "..\\..\\escape",
        "sub/dir",
        "sub\\dir",
        "/etc/passwd",
        "C:\\Windows",
        "task;rm -rf",
        "task with spaces",
        "",
    ]

    for bad_id in dangerous_ids:
        with pytest.raises(GitError, match="Invalid task ID|cannot be empty"):
            await svc.create_worktree(repo_dir, bad_id, "main")


@pytest.mark.asyncio
async def test_remove_worktree_path_traversal_rejection(git_repo):
    """remove_worktree refuses to touch directories outside workspace root."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    # Try to target repo_dir or parent
    with pytest.raises(GitError, match="outside workspace root"):
        await svc.remove_worktree(repo_dir, repo_dir)

    with pytest.raises(GitError, match="outside workspace root"):
        await svc.remove_worktree(repo_dir, "C:/Windows")


@pytest.mark.asyncio
async def test_rapid_resets_create_unique_backup_refs(git_repo):
    """Multiple rapid resets within milliseconds generate unique backup refs without collisions."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]

    # 1. Create worktree and commit 1
    wt = await svc.create_worktree(repo_dir, "task-rapid", "main")
    f1 = os.path.join(wt, "f1.txt")
    with open(f1, "w", encoding="utf-8") as f:
        f.write("commit 1\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=wt, check=True)

    # 2. Reset 1
    await svc.create_worktree(repo_dir, "task-rapid", "main", reset_branch=True)

    # 3. Commit 2 on new branch
    f2 = os.path.join(wt, "f2.txt")
    with open(f2, "w", encoding="utf-8") as f:
        f.write("commit 2\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=wt, check=True)

    # 4. Reset 2 immediately
    await svc.create_worktree(repo_dir, "task-rapid", "main", reset_branch=True)

    # 5. Check all backup refs
    res = subprocess.run(
        ["git", "for-each-ref", "refs/forgeflow/backups/", "--format=%(refname)"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True
    )
    backup_refs = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
    rapid_refs = [r for r in backup_refs if "task_task-rapid_" in r]

    # Must have produced exactly 2 distinct backup references
    assert len(rapid_refs) == 2
    assert rapid_refs[0] != rapid_refs[1]


@pytest.mark.asyncio
async def test_prune_worktrees_removes_orphaned_metadata_safely(git_repo):
    """prune_worktrees removes dead/orphaned worktree metadata without affecting live unrelated worktrees."""
    svc: GitService = git_repo["service"]
    repo_dir = git_repo["repo_dir"]
    tmp_parent = os.path.dirname(repo_dir)

    # 1. Create a live manual worktree
    manual_wt = os.path.join(tmp_parent, "safe-manual-wt")
    subprocess.run(
        ["git", "worktree", "add", "-b", "safe-manual-branch", manual_wt, "main"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    assert os.path.exists(manual_wt)

    # 2. Create a task worktree
    task_wt = await svc.create_worktree(repo_dir, "task-to-orphan", "main")
    assert os.path.exists(task_wt)

    # Both worktrees should be registered
    wts_before = await svc.list_worktrees(repo_dir)
    assert any(os.path.normcase(w.get("worktree", "")) == os.path.normcase(task_wt) for w in wts_before)
    assert any(os.path.normcase(w.get("worktree", "")) == os.path.normcase(manual_wt) for w in wts_before)

    # 3. Simulate external rogue deletion of task_wt from disk (without git worktree remove)
    shutil.rmtree(task_wt)
    assert not os.path.exists(task_wt)

    # 4. Prune worktrees
    await svc.prune_worktrees(repo_dir)

    # 5. Verify task_wt metadata was pruned, but manual_wt is STILL registered and alive
    wts_after = await svc.list_worktrees(repo_dir)
    assert not any(os.path.normcase(w.get("worktree", "")) == os.path.normcase(task_wt) for w in wts_after)
    assert any(os.path.normcase(w.get("worktree", "")) == os.path.normcase(manual_wt) for w in wts_after)
    assert os.path.exists(manual_wt)

    # Cleanup
    subprocess.run(["git", "worktree", "remove", "--force", manual_wt], cwd=repo_dir, capture_output=True)


@pytest.mark.asyncio

async def test_windows_selector_event_loop_fallback(git_repo):
    import sys
    import asyncio
    from unittest.mock import patch

    repo_path = git_repo["repo_dir"]
    service = git_repo["service"]
    
    # We patch create_subprocess_exec to always raise NotImplementedError
    # to simulate Windows SelectorEventLoop environment
    with patch('asyncio.create_subprocess_exec', side_effect=NotImplementedError):
        # This should hit the fallback and still succeed
        is_repo = await service.is_git_repository(repo_path)
        assert is_repo is True
        
        # Test a failing command too
        try:
            await service.create_worktree(repo_path, 'fake_task', 'nonexistent_branch')
            assert False, 'Should have raised GitError'
        except GitError:
            pass
