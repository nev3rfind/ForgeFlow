import asyncio
import json
import logging
from typing import AsyncGenerator, Type, Dict, Any, List
from pydantic import BaseModel
import time

from app.integrations.base import BaseProvider
from app.integrations.desktop_rpa_engine import DesktopRPAEngine, RPAEngineError

logger = logging.getLogger(__name__)

class AgyDesktopAdapter(BaseProvider):
    """
    Adapter that drives the Antigravity Desktop App via Robotic Process Automation (RPA).
    This mimics an API by physically pasting prompts into the app and extracting the response.
    """
    
    def __init__(self, window_title: str = ".*Antigravity.*"):
        self.rpa = DesktopRPAEngine(app_title_regex=window_title)
        
    def is_available(self) -> bool:
        # Check if the pywinauto dependencies are loaded and windows exist
        try:
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=self.rpa.app_title_regex)
            return len(windows) > 0
        except Exception:
            return False

    async def chat(self, prompt: str, schema: Type[BaseModel], system_instruction: str, workspaces: List[str]) -> BaseModel:
        # We will wrap the stream_chat logic to return the final object
        structured_data = None
        async for chunk in self.stream_chat(prompt, schema, system_instruction, workspaces):
            if chunk.get("type") == "structured_output":
                structured_data = chunk.get("data")
                
        if structured_data:
            return schema.model_validate(structured_data)
        
        raise RuntimeError("No structured output returned from Desktop RPA")

    async def stream_chat(
        self, 
        prompt: str, 
        schema: Type[BaseModel], 
        system_instruction: str, 
        workspaces: List[str],
        model: str = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        
        logger.info("Starting Desktop RPA sequence for Antigravity...")
        yield {"type": "event", "content": "[RPA] Connecting to Antigravity Desktop App..."}
        
        try:
            # 1. Connect and focus
            self.rpa.connect()
            yield {"type": "event", "content": "[RPA] Application focused."}
            
            # Format the full prompt with schema expectation
            schema_format = json.dumps(schema.model_json_schema(), indent=2)
            full_prompt = (
                f"{system_instruction}\n\n"
                f"--- TASK ---\n{prompt}\n\n"
                f"--- OUTPUT SPECIFICATION ---\n"
                f"You MUST respond ONLY with a valid JSON object matching this schema:\n{schema_format}"
            )
            
            # 2. Focus input box and paste
            # We assume the chat box is either active, or can be reached via a shortcut or simple click.
            # For robustness in unknown Electron structures without exact inspect, we will send tab a few times
            # or try to directly find the "Edit" control.
            try:
                # Electron usually exposes the chat input as an Edit control.
                edit_box = self.rpa.main_window.child_window(control_type="Edit", found_index=0)
                edit_box.set_focus()
            except Exception as e:
                logger.warning(f"RPA: Could not find UIA Edit control: {e}. Relying on active focus.")
            
            self.rpa.paste_text(full_prompt)
            yield {"type": "event", "content": "[RPA] Prompt pasted."}
            
            # 3. Submit
            self.rpa.send_keystrokes('{ENTER}')
            yield {"type": "event", "content": "[RPA] Task submitted. Waiting for AI to process..."}
            
            # 4. Wait for generation to complete
            # This is complex in a black-box app. We will monitor the clipboard by sending a copy command
            # every few seconds, and when the text stops changing for a while or matches JSON, we assume it's done.
            # Another approach: wait for a UIA 'Copy' button on the message.
            
            last_text = ""
            stable_count = 0
            
            # Start a background polling loop (simulated as async)
            # To extract, we'll try to find the last message block or just rely on Ctrl+A, Ctrl+C in a specific zone.
            # A safer method for Electron chat apps: focus the last message and copy. 
            # We will send Shift+Tab to focus the last message block, then Ctrl+C.
            
            for _ in range(120): # Max 4 minutes (120 * 2s)
                await asyncio.sleep(2.0)
                
                # Try to copy the last message. In many AI apps, Ctrl+Shift+C copies the last response.
                # If not, we will attempt to find all 'Text' controls and get the last one.
                try:
                    # In UIA, we can extract text without clipboard if the app exposes it!
                    text_elements = self.rpa.main_window.descendants(control_type="Text")
                    if text_elements:
                        # The last few text elements usually contain the latest response
                        current_text = "\n".join([t.texts()[0] for t in text_elements[-10:] if t.texts()])
                        
                        if current_text == last_text and current_text.strip():
                            stable_count += 1
                        else:
                            last_text = current_text
                            stable_count = 0
                            
                        # If the text hasn't changed in 4 seconds (2 loops) and contains valid JSON, we might be done.
                        if stable_count >= 2 and "{" in current_text and "}" in current_text:
                            yield {"type": "event", "content": "[RPA] Generation appears complete."}
                            break
                except Exception:
                    pass
                    
            # 5. Extract JSON
            # We will try to parse the last_text to find the JSON schema
            import re
            
            # Look for ```json ... ```
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', last_text, re.DOTALL)
            raw_json_str = None
            if match:
                raw_json_str = match.group(1)
            else:
                # Fallback to outermost braces
                match = re.search(r'(\{[\s\\S]*\})', last_text)
                if match:
                    raw_json_str = match.group(1)
                    
            if not raw_json_str:
                raise RPAEngineError("Could not extract JSON from the Desktop App response.")
                
            parsed = json.loads(raw_json_str)
            validated = schema.model_validate(parsed)
            
            yield {"type": "structured_output", "data": validated.model_dump()}
            
        except Exception as e:
            logger.error(f"Desktop RPA Sequence Failed: {e}")
            yield {"type": "event", "content": f"[RPA ERROR] {e}"}
            raise
