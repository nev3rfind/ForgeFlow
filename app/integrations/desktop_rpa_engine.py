import time
import pyperclip
import logging
from pywinauto import Desktop, Application
from pywinauto.keyboard import send_keys

logger = logging.getLogger(__name__)

class RPAEngineError(Exception):
    pass

class DesktopRPAEngine:
    def __init__(self, app_title_regex: str, backend: str = "uia"):
        self.app_title_regex = app_title_regex
        self.backend = backend
        self.app = None
        self.main_window = None

    def connect(self):
        """Attempts to locate the application window and bring it to the foreground."""
        try:
            logger.info(f"RPA: Searching for window matching '{self.app_title_regex}'")
            
            import ctypes
            import re
            
            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            matches = []
            pattern = re.compile(self.app_title_regex, re.IGNORECASE)

            def foreach_window(hwnd, lParam):
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLength(hwnd)
                    if 0 < length < 10000:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(hwnd, buff, length + 1)
                        title = buff.value
                        if pattern.search(title):
                            matches.append(hwnd)
                return True

            EnumWindows(EnumWindowsProc(foreach_window), 0)
            
            if not matches:
                raise RPAEngineError(f"No window found matching '{self.app_title_regex}'")
            
            hwnd = matches[0]
            self.app = Application(backend=self.backend).connect(handle=hwnd)
            self.main_window = self.app.window(handle=hwnd)
            
            # Bring to foreground safely
            try:
                self.main_window.set_focus()
            except Exception as e:
                logger.warning(f"RPA: Could not set exact focus, attempting workaround: {e}")
                self.main_window.minimize()
                self.main_window.restore()
                self.main_window.set_focus()
                
            return True
        except Exception as e:
            logger.error(f"RPA Connection Error: {e}")
            raise RPAEngineError(f"Failed to connect to application: {e}")

    def paste_text(self, text: str):
        """Pastes text directly from the clipboard to avoid slow keyboard typing."""
        if not self.main_window:
            raise RPAEngineError("Not connected to any application")
            
        logger.debug("RPA: Pasting text via clipboard")
        # Save old clipboard content
        old_clipboard = pyperclip.paste()
        try:
            pyperclip.copy(text)
            time.sleep(0.1) # Small delay to ensure clipboard is ready
            # Send Ctrl+V
            send_keys('^v')
            time.sleep(0.1)
        finally:
            # Optionally restore old clipboard, but it might interfere if pasted async
            pass

    def send_keystrokes(self, keys: str):
        """Sends key strokes to the active window."""
        logger.debug(f"RPA: Sending keystrokes: {keys}")
        send_keys(keys)
        time.sleep(0.1)

    def read_clipboard(self) -> str:
        """Reads current text from the clipboard."""
        return pyperclip.paste()
        
    def wait_for_ui_ready(self, timeout_secs: int = 120, check_interval: float = 2.0):
        """
        Generic wait function. Because electron apps don't easily expose busy states,
        this will likely need to be customized per-app (e.g. searching for a 'Stop' button).
        """
        # For now, this is a placeholder that adapters can build on top of.
        pass
