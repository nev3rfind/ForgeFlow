import os
import google.antigravity as ag
from app.integrations.provider import AgentProvider
from app.config import get_env_or_registry
from pydantic import BaseModel, ValidationError
from typing import AsyncGenerator, Dict, Any, Type, Optional
import json
import re

class AntigravityProviderError(Exception):
    """Raised when the Antigravity provider fails to produce valid structured output."""
    pass

class AntigravityProvider(AgentProvider):
    name = "Antigravity"

    def __init__(self, api_key: str | None = None):
        if not api_key:
            api_key = get_env_or_registry("GEMINI_API_KEY")
        if api_key and "GEMINI_API_KEY" not in os.environ:
            os.environ["GEMINI_API_KEY"] = api_key
        self.api_key = api_key

    def _build_config(self, schema: Type[BaseModel], system_instruction: str, workspaces: list[str]):
        finish_instruction = (
            "\n\nCRITICAL OUTPUT INSTRUCTION:\n"
            "When you are finished with the task, you MUST call the `finish` tool exactly once, "
            "passing arguments that conform to the required response schema. "
            "Do NOT respond with the final answer as plain conversational text, and do NOT call "
            "`finish` more than once. The `finish` tool call is the ONLY way to deliver your final answer."
        )
        combined_instruction = f"{system_instruction}{finish_instruction}"

        return ag.LocalAgentConfig(
            system_instructions=combined_instruction,
            workspaces=workspaces,
            response_schema=schema,
            api_key=self.api_key
        )

    @staticmethod
    def _coerce_output(output: Any) -> Any:
        """Normalize structured output to a plain dict.

        The SDK returns the parsed payload from json.loads (a dict), but a
        Pydantic model is also accepted so callers always get a dict.
        """
        if output is None:
            return None
        if isinstance(output, BaseModel):
            return output.model_dump()
        if isinstance(output, dict):
            return output
        return {"value": output}

    @staticmethod
    def _extract_json(raw_text: str) -> Dict[str, Any]:
        """Best-effort extraction of a JSON object from free-form response text."""
        cleaned = (raw_text or "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except Exception:
                pass

        match = re.search(r'(\{[\s\S]*\})', raw_text or "")
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        raise AntigravityProviderError(
            "Antigravity did not invoke the finish tool and its response text did not "
            f"contain valid JSON matching the required schema. Raw response: {raw_text[:300]!r}"
        )

    def _validate_or_fallback(self, structured: Any, response_text: Optional[str], schema: Type[BaseModel]) -> BaseModel:
        coerced = self._coerce_output(structured)
        if coerced is not None:
            return schema.model_validate(coerced)

        parsed = self._extract_json(response_text or "")
        try:
            return schema.model_validate(parsed)
        except ValidationError as e:
            raise AntigravityProviderError(
                f"Antigravity structured output was not produced and the fallback JSON did not "
                f"match the required schema: {e}"
            )

    async def chat(self, prompt: str, schema: Type[BaseModel], system_instruction: str, workspaces: list[str]) -> BaseModel:
        config = self._build_config(schema, system_instruction, workspaces)

        async with ag.Agent(config) as agent:
            response = await agent.chat(prompt)
            output = await response.structured_output()
            if output is None:
                text = await response.text()
                return self._validate_or_fallback(None, text, schema)
            return self._validate_or_fallback(output, None, schema)

    async def stream_chat(self, prompt: str, schema: Type[BaseModel], system_instruction: str, workspaces: list[str]) -> AsyncGenerator[Dict[str, Any], None]:
        config = self._build_config(schema, system_instruction, workspaces)

        async with ag.Agent(config) as agent:
            response = await agent.chat(prompt)

            accumulated_text = ""
            async for chunk in response.chunks:
                if isinstance(chunk, ag.types.Text):
                    accumulated_text += chunk.text
                    yield {"type": "text", "content": chunk.text}
                elif isinstance(chunk, ag.types.Thought):
                    yield {"type": "thought", "content": chunk.text}
                elif isinstance(chunk, ag.types.ToolCall):
                    yield {"type": "tool_call", "name": str(chunk.name), "args": chunk.args}
                elif isinstance(chunk, ag.types.ToolResult):
                    yield {"type": "tool_result", "name": str(chunk.name), "result": str(chunk.result)}

            output = await response.structured_output()
            validated = self._validate_or_fallback(output, accumulated_text, schema)
            yield {"type": "structured_output", "data": validated.model_dump()}
