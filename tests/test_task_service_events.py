import pytest
from app.models import TaskState, Event
from app.state import Database, Repository
from app.events.bus import EventBus
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_state_changed_event_contains_error(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    repo = Repository(db)
    bus = EventBus()
    service = TaskService(repo, bus)

    # Create task
    task = await service.create_task(
        project_id="proj-1",
        title="Test Error Visibility",
        description="Verify error is dispatched in STATE_CHANGED"
    )

    received_events = []

    async def event_handler(event: Event):
        received_events.append(event)

    bus.subscribe(task.id, event_handler)

    test_error_message = "Git worktree failure: fatal: A branch named 'task/xyz' already exists."

    # Update status with an error
    updated_task = await service.update_status(
        task_id=task.id,
        status=TaskState.FAILED,
        agent="Antigravity / Investigator",
        error=test_error_message
    )

    # 1. Verify task model in database has the error
    assert updated_task is not None
    assert updated_task.status == TaskState.FAILED
    assert updated_task.error_information == test_error_message

    reloaded = service.get_task(task.id)
    assert reloaded.error_information == test_error_message

    # 2. Verify WebSocket / EventBus STATE_CHANGED event payload contains the error
    state_events = [e for e in received_events if e.event_type == "STATE_CHANGED"]
    assert len(state_events) == 1

    event_payload = state_events[0].payload
    assert event_payload["old_status"] == "PENDING"
    assert event_payload["new_status"] == "FAILED"
    assert event_payload["agent"] == "Antigravity / Investigator"
    assert event_payload["error"] == test_error_message

    # 3. Verify format compatible with dashboard eventSummary
    assert "error" in event_payload
    summary_repr = f"{event_payload['old_status']} -> {event_payload['new_status']}  [Error: {event_payload['error']}]"
    assert "Git worktree failure" in summary_repr


@pytest.mark.asyncio
async def test_websocket_unsubscribes_on_unexpected_exception():
    """Verify guaranteed cleanup: event_bus callback is removed even on unexpected connection drop."""
    import asyncio
    from unittest.mock import AsyncMock
    from app.main import websocket_endpoint, event_bus
    from datetime import datetime, timezone

    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock(side_effect=RuntimeError("Abrupt socket drop / ConnectionResetError"))

    task_id = "test-ws-task-unsub"

    ws_task = asyncio.create_task(websocket_endpoint(mock_ws, task_id))

    await asyncio.sleep(0.05)
    assert task_id in event_bus.subscribers
    assert len(event_bus.subscribers[task_id]) == 1

    # Publish event to trigger send_json
    test_event = Event(
        task_id=task_id,
        event_type="STATE_CHANGED",
        payload={"new_status": "INVESTIGATING"},
        timestamp=datetime.now(timezone.utc)
    )
    await event_bus.publish(test_event)

    # Wait for the task to finish with the expected error
    with pytest.raises(RuntimeError, match="Abrupt socket drop"):
        await ws_task

    # Verify callback is guaranteed to be cleaned up
    assert len(event_bus.subscribers.get(task_id, [])) == 0
