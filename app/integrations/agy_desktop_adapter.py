import asyncio
import json
import logging
from typing import AsyncGenerator, Type, Dict, Any, List
from pydantic import BaseModel
import time

from app.integrations.provider import AgentProvider
from app.integrations.desktop_rpa_engine import DesktopRPAEngine, RPAEngineError

logger = logging.getLogger(__name__)

class AgyDesktopAdapter(AgentProvider):
    """
    Adapter that drives the Antigravity Desktop App via Robotic Process Automation (RPA).
    This mimics an API by physically pasting prompts into the app and extracting the response.
    """
    
    def __init__(self, window_title: str = ".*Antigravity.*"):
        self.rpa = DesktopRPAEngine(app_title_regex=window_title)
        
    def is_available(self) -> bool:
        try:
            best_window, _ = self.rpa._find_robust_antigravity_window()
            return best_window is not None
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
                    current_text = ""
                    # Fast UIA text extraction
                    text_elements = self.rpa.main_window.descendants(control_type="Text")
                    if text_elements:
                        current_text = "\n".join([t.texts()[0] for t in text_elements[-15:] if t.texts()])
                    else:
                        # Blur input box using ESC or TAB to allow global shortcut
                        self.rpa.send_keystrokes('{ESC}')
                        await asyncio.sleep(0.1)
                        # Fallback to clipboard if UIA fails
                        self.rpa.send_keystrokes('^a^c')
                        await asyncio.sleep(0.5)
                        current_text = self.rpa.read_clipboard()
                        
                    if current_text and current_text == last_text and current_text.strip():
                        stable_count += 1
                    else:
                        last_text = current_text
                        stable_count = 0
                        
                    # If the text hasn't changed in 4 seconds (2 loops) and contains valid JSON, we might be done.
                    if stable_count >= 2 and "{" in current_text and "}" in current_text:
                        yield {"type": "event", "content": "[RPA] Generation appears complete."}
                        break
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"RPA extraction loop warning: {e}")
                    
            # 5. Extract JSON
            # We will try to parse the last_text to find the JSON schema
            import re
            
            # Look for ```json ... ``` (use finditer to get the LAST one in case of chat history)
            matches = list(re.finditer(r'```(?:json)?\s*(\{.*?\})\s*```', last_text, re.DOTALL))
            raw_json_str = None
            if matches:
                raw_json_str = matches[-1].group(1)
            else:
                # Bracket matching from the end to find the outermost valid JSON object
                open_braces = 0
                end_idx = last_text.rfind('}')
                if end_idx != -1:
                    for i in range(end_idx, -1, -1):
                        if last_text[i] == '}':
                            open_braces += 1
                        elif last_text[i] == '{':
                            open_braces -= 1
                            if open_braces == 0:
                                raw_json_str = last_text[i:end_idx+1]
                                break
                    
            if not raw_json_str:
                raise RPAEngineError(f"Could not extract JSON from the Desktop App response. Raw text was: {last_text}")
                
            parsed = json.loads(raw_json_str)
            validated = schema.model_validate(parsed)
            
            yield {"type": "structured_output", "data": validated.model_dump()}
            
        except Exception as e:
            logger.error(f"Desktop RPA Sequence Failed: {e}")
            yield {"type": "event", "content": f"[RPA ERROR] {e}"}
            raise
