import asyncio
from typing import Callable, Awaitable, List, Dict, Any
from app.models.event import Event
from datetime import datetime
import uuid

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[Event], Awaitable[None]]]] = {}

    def subscribe(self, task_id: str, callback: Callable[[Event], Awaitable[None]]):
        if task_id not in self.subscribers:
            self.subscribers[task_id] = []
        self.subscribers[task_id].append(callback)

    def unsubscribe(self, task_id: str, callback: Callable[[Event], Awaitable[None]]):
        if task_id in self.subscribers and callback in self.subscribers[task_id]:
            self.subscribers[task_id].remove(callback)

    async def publish(self, event: Event):
        if event.task_id in self.subscribers:
            callbacks = self.subscribers[event.task_id]
            for cb in callbacks:
                try:
                    await cb(event)
                except Exception as e:
                    print(f"Error in event subscriber: {e}")

    async def publish_raw(self, task_id: str, event_type: str, payload: Dict[str, Any]):
        event = Event(
            id=str(uuid.uuid4()),
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            timestamp=datetime.utcnow()
        )
        await self.publish(event)
