import pytest
from app.models import Artifact
from app.state import Database, Repository


def test_artifact_upsert_prevents_duplicates(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    repo = Repository(db)

    task_id = "test-task-art-1"

    # First run saves TASK.md
    art1 = Artifact(task_id=task_id, name="TASK.md", path="/path/to/v1/TASK.md")
    repo.save_artifact(art1)

    artifacts = repo.get_artifacts(task_id)
    assert len(artifacts) == 1
    assert artifacts[0].name == "TASK.md"
    assert artifacts[0].path == "/path/to/v1/TASK.md"

    # Second run (or retry) saves updated TASK.md
    art2 = Artifact(task_id=task_id, name="TASK.md", path="/path/to/v2/TASK.md")
    repo.save_artifact(art2)

    # Must NOT produce a second record for TASK.md
    artifacts_updated = repo.get_artifacts(task_id)
    assert len(artifacts_updated) == 1
    assert artifacts_updated[0].name == "TASK.md"
    assert artifacts_updated[0].path == "/path/to/v2/TASK.md"
    assert artifacts_updated[0].id == art1.id  # Preserves record identity

    # Saving a DIFFERENT artifact type creates a second entry
    art3 = Artifact(task_id=task_id, name="ROOT_CAUSE.md", path="/path/to/ROOT_CAUSE.md")
    repo.save_artifact(art3)

    artifacts_final = repo.get_artifacts(task_id)
    assert len(artifacts_final) == 2
    names = {a.name for a in artifacts_final}
    assert names == {"TASK.md", "ROOT_CAUSE.md"}


def test_delete_artifacts_for_task(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    repo = Repository(db)

    task_id = "test-task-del"
    repo.save_artifact(Artifact(task_id=task_id, name="A.md", path="/a"))
    repo.save_artifact(Artifact(task_id=task_id, name="B.md", path="/b"))

    assert len(repo.get_artifacts(task_id)) == 2
    deleted_count = repo.delete_artifacts(task_id)
    assert deleted_count == 2
    assert len(repo.get_artifacts(task_id)) == 0
