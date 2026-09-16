import pytest
import os
from fastapi.testclient import TestClient

def test_health_and_dashboard_endpoints():
    from app.main import app
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "abacus_reviewer_enabled" in data
    assert "abacus_review_mode" in data

    # Test dashboard
    res_dash = client.get("/")
    assert res_dash.status_code == 200
    assert "ForgeFlow Command Center" in res_dash.text

    # Test projects endpoint
    res_proj = client.get("/projects")
    assert res_proj.status_code == 200
    assert isinstance(res_proj.json(), list)

    # Test tasks endpoint
    res_tasks = client.get("/tasks")
    assert res_tasks.status_code == 200
    assert isinstance(res_tasks.json(), list)
