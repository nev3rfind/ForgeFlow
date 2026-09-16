import asyncio
import os
import re
import shutil
import time
import uuid
from typing import Optional, Tuple, List, Dict, Any

class GitError(Exception):
    pass

class GitService:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(os.path.normpath(workspace_root))
        if not os.path.exists(self.workspace_root):
            os.makedirs(self.workspace_root, exist_ok=True)

    def _validate_task_id(self, task_id: str) -> str:
        if not task_id or not isinstance(task_id, str):
            raise GitError("Task ID cannot be empty")
        clean_id = task_id.strip()
        if not re.match(r"^[a-zA-Z0-9_\-]+$", clean_id):
            raise GitError(f"Invalid task ID '{task_id}': contains forbidden characters")
        
        worktree_name = f"forgeflow_task_{clean_id}"
        worktree_path = os.path.abspath(os.path.normpath(os.path.join(self.workspace_root, worktree_name)))
        
        try:
            common = os.path.commonpath([os.path.normcase(self.workspace_root), os.path.normcase(worktree_path)])
            if common != os.path.normcase(self.workspace_root) or os.path.normcase(worktree_path) == os.path.normcase(self.workspace_root):
                raise GitError(f"Task ID '{task_id}' resolves outside workspace root")
        except ValueError:
            raise GitError(f"Task ID '{task_id}' resolves to an invalid drive or path")
            
        return worktree_path

    def _validate_worktree_path(self, worktree_path: str) -> str:
        if not worktree_path or not isinstance(worktree_path, str):
            raise GitError("Worktree path cannot be empty")
        norm_path = os.path.abspath(os.path.normpath(worktree_path))
        try:
            common = os.path.commonpath([os.path.normcase(self.workspace_root), os.path.normcase(norm_path)])
            if common != os.path.normcase(self.workspace_root) or os.path.normcase(norm_path) == os.path.normcase(self.workspace_root):
                raise GitError(f"Worktree path '{worktree_path}' is outside workspace root '{self.workspace_root}'")
        except ValueError:
            raise GitError(f"Worktree path '{worktree_path}' resolves to a different drive")
        return norm_path

    async def _run_git(self, repo_path: str, *args) -> Tuple[int, str, str]:
        cmd = ['git', '-c', 'core.longpaths=true'] + list(args)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        out_str = stdout.decode('utf-8', errors='replace').strip()
        err_str = stderr.decode('utf-8', errors='replace').strip()
        return process.returncode, out_str, err_str

    async def prune_worktrees(self, repo_path: str) -> bool:
        """Prune dead worktree metadata from .git/worktrees where working directory no longer exists on disk."""
        repo_path = os.path.abspath(os.path.normpath(repo_path))
        if not await self.is_git_repository(repo_path):
            raise GitError(f"Not a git repository: {repo_path}")
        code, _, stderr = await self._run_git(repo_path, 'worktree', 'prune')
        if code != 0:
            raise GitError(f"Failed to prune worktrees: {stderr}")
        return True

    async def is_git_repository(self, repo_path: str) -> bool:
        if not repo_path or not os.path.exists(repo_path):
            return False
        code, stdout, _ = await self._run_git(repo_path, 'rev-parse', '--is-inside-work-tree')
        return code == 0 and stdout.strip().lower() == 'true'

    async def is_clean(self, repo_path: str) -> bool:
        code, stdout, stderr = await self._run_git(repo_path, 'status', '--porcelain')
        if code != 0:
            err_msg = stderr or stdout or f"exit code {code}"
            raise GitError(f"Git status failed: {err_msg}")
        return len(stdout) == 0

    async def get_current_branch(self, repo_path: str) -> str:
        code, stdout, stderr = await self._run_git(repo_path, 'branch', '--show-current')
        if code != 0:
            err_msg = stderr or stdout or f"exit code {code}"
            raise GitError(f"Git branch failed: {err_msg}")
        return stdout

    async def list_worktrees(self, repo_path: str) -> List[Dict[str, Any]]:
        """Return a list of worktree descriptors from git worktree list --porcelain."""
        code, stdout, _ = await self._run_git(repo_path, 'worktree', 'list', '--porcelain')
        if code != 0:
            return []
        worktrees = []
        current: Dict[str, Any] = {}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
                continue
            if line.startswith('worktree '):
                if current:
                    worktrees.append(current)
                    current = {}
                raw_path = line[len('worktree '):].strip()
                current['worktree'] = os.path.abspath(os.path.normpath(raw_path))
            elif line.startswith('branch '):
                current['branch'] = line[len('branch '):].strip()
            elif line == 'bare':
                current['bare'] = True
            elif line == 'detached':
                current['detached'] = True
            elif line.startswith('HEAD '):
                current['head'] = line[len('HEAD '):].strip()
        if current:
            worktrees.append(current)
        return worktrees

    async def create_worktree(
        self, repo_path: str, task_id: str, base_branch: Optional[str] = None, reset_branch: bool = False
    ) -> str:
        repo_path = os.path.abspath(os.path.normpath(repo_path))
        if not await self.is_git_repository(repo_path):
            raise GitError(f"Not a git repository: {repo_path}")

        # Validate task_id and construct safe worktree_path
        worktree_path = self._validate_task_id(task_id)
        branch_name = f"task/{task_id.strip()}"

        # Resolve base branch if not provided
        if not base_branch:
            base_branch = await self.get_current_branch(repo_path)
        if not base_branch:
            base_branch = "HEAD"

        # 1. Prune any stale/dead worktree metadata first
        await self.prune_worktrees(repo_path)

        # 2. Check if worktree_path is already registered in Git
        existing_wts = await self.list_worktrees(repo_path)
        target_norm = os.path.normcase(worktree_path)
        is_registered = any(os.path.normcase(wt.get('worktree', '')) == target_norm for wt in existing_wts)

        if is_registered:
            code, stdout, stderr = await self._run_git(repo_path, 'worktree', 'remove', '--force', worktree_path)
            await self.prune_worktrees(repo_path)

        # 3. Clean up disk directory if it still exists
        if os.path.exists(worktree_path):
            try:
                shutil.rmtree(worktree_path)
            except Exception:
                await asyncio.sleep(0.1)
                shutil.rmtree(worktree_path, ignore_errors=True)

        # 4. Prune again
        await self.prune_worktrees(repo_path)

        # 5. Ensure workspace_root exists
        os.makedirs(self.workspace_root, exist_ok=True)

        # 6. Check if task branch already exists in Git
        code, _, _ = await self._run_git(repo_path, 'rev-parse', '--verify', f'refs/heads/{branch_name}')
        branch_exists = (code == 0)

        if branch_exists:
            if reset_branch:
                # Explicit reset requested: back up any unique commits before resetting
                count_code, count_out, _ = await self._run_git(
                    repo_path, 'rev-list', '--count', f'{base_branch}..{branch_name}'
                )
                if count_code == 0 and int(count_out.strip() or 0) > 0:
                    clean_branch = branch_name.replace('/', '_')
                    timestamp_ms = int(time.time() * 1000)
                    unique_suffix = uuid.uuid4().hex[:8]
                    backup_ref = f"refs/forgeflow/backups/{clean_branch}_{timestamp_ms}_{unique_suffix}"
                    ref_code, ref_out, ref_err = await self._run_git(
                        repo_path, 'update-ref', backup_ref, f'refs/heads/{branch_name}'
                    )
                    if ref_code != 0:
                        raise GitError(f"Failed to create backup ref '{backup_ref}': {ref_err or ref_out}")

                code, stdout, stderr = await self._run_git(
                    repo_path, 'worktree', 'add', '-B', branch_name, worktree_path, base_branch
                )
            else:
                # Preserve existing commits by checking out the existing branch
                code, stdout, stderr = await self._run_git(
                    repo_path, 'worktree', 'add', worktree_path, branch_name
                )
        else:
            # Branch does not exist: create new branch starting from base_branch
            code, stdout, stderr = await self._run_git(
                repo_path, 'worktree', 'add', '-b', branch_name, worktree_path, base_branch
            )

        if code != 0:
            err_msg = stderr or stdout or f"exit code {code}"
            raise GitError(f"Failed to create worktree: {err_msg}")

        return worktree_path

    async def remove_worktree(self, repo_path: str, worktree_path: str):
        repo_path = os.path.abspath(os.path.normpath(repo_path))
        worktree_path = self._validate_worktree_path(worktree_path)

        existing_wts = await self.list_worktrees(repo_path)
        target_norm = os.path.normcase(worktree_path)
        is_registered = any(os.path.normcase(wt.get('worktree', '')) == target_norm for wt in existing_wts)

        if is_registered:
            code, stdout, stderr = await self._run_git(repo_path, 'worktree', 'remove', '--force', worktree_path)
            if code != 0 and os.path.exists(worktree_path):
                await self.prune_worktrees(repo_path)

        if os.path.exists(worktree_path):
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception:
                pass

        await self.prune_worktrees(repo_path)

