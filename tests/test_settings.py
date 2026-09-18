import pytest
from fastapi.testclient import TestClient
from app.main import app, repo
from app.models import TaskState

@pytest.fixture
def client():
    return TestClient(app)

def test_reset_config(client):
    response = client.post("/settings/reset-config")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

def test_reset_data_blocks_active_tasks(client):
    client.post("/projects", json={"name": "p", "repository": "r", "type": "python"})
    projects = client.get("/projects").json()
    pid = projects[0]["id"]
    
    response = client.post("/tasks", json={"project_id": pid, "title": "t", "description": "d"})
    task_id = response.json()["id"]
    
    response = client.post("/settings/reset-data")
    assert response.status_code == 400
    assert "tasks are active" in response.json()["detail"]
    
    from app.main import task_service
    task_service.delete_task(task_id)

def test_reset_data_wipes_when_safe(client):
    client.post("/projects", json={"name": "p", "repository": "r", "type": "python"})
    projects = client.get("/projects").json()
    pid = projects[0]["id"]
    
    response = client.post("/tasks", json={"project_id": pid, "title": "t", "description": "d"})
    task_id = response.json()["id"]
    
    # set to completed directly in DB
    from app.main import db
    with db._get_connection() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (TaskState.COMPLETED, task_id))
    
    response = client.post("/settings/reset-data")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    
    assert len(repo.get_tasks()) == 0
