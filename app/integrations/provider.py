from typing import Optional, Dict, Any, AsyncGenerator
from abc import ABC, abstractmethod
from pydantic import BaseModel

class AgentProvider(ABC):
    @abstractmethod
    async def chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str]) -> Any:
        pass
        
    @abstractmethod
    async def stream_chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str]) -> AsyncGenerator[Dict[str, Any], None]:
        pass
