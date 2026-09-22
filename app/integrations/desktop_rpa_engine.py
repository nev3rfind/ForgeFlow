import time
import pyperclip
import logging
import ctypes
from ctypes.wintypes import DWORD, MAX_PATH, HWND, LPARAM
import re
from pywinauto import Application
from pywinauto.keyboard import send_keys

logger = logging.getLogger(__name__)

class RPAEngineError(Exception):
    def __init__(self, message, diagnostic=""):
        super().__init__(message)
        self.diagnostic = diagnostic

class DesktopRPAEngine:
    def __init__(self, app_title_regex: str, backend: str = "uia"):
        self.app_title_regex = app_title_regex
        self.backend = backend
        self.app = None
        self.main_window = None

    def _get_process_info_by_hwnd(self, hwnd):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        
        pid = DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hProcess = kernel32.OpenProcess(0x0410 | 0x0010, False, pid)
        if not hProcess:
            hProcess = kernel32.OpenProcess(0x0410, False, pid)
            if not hProcess:
                return "", ""
                
        exe_base = ctypes.create_unicode_buffer(MAX_PATH)
        psapi.GetModuleBaseNameW(hProcess, None, exe_base, MAX_PATH)
        
        exe_path = ctypes.create_unicode_buffer(MAX_PATH)
        psapi.GetModuleFileNameExW(hProcess, None, exe_path, MAX_PATH)
        
        kernel32.CloseHandle(hProcess)
        return exe_base.value.lower(), exe_path.value.lower()

    def _find_robust_antigravity_window(self):
        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        GetWindowText = user32.GetWindowTextW
        GetWindowTextLength = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible

        candidates = []
        diagnostics = []
        
        title_pattern = re.compile(r'^(Google\s+)?Antigravity(\s+IDE)?$', re.IGNORECASE)
        broad_title_pattern = re.compile(self.app_title_regex, re.IGNORECASE)

        def foreach_window(hwnd, lParam):
            if not IsWindowVisible(hwnd):
                return True
                
            length = GetWindowTextLength(hwnd)
            if not (0 < length < 10000):
                return True
                
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value.strip()
            
            proc_name, proc_path = self._get_process_info_by_hwnd(hwnd)
            is_antigravity_process = (proc_name == "antigravity.exe") or ("antigravity" in proc_path.lower())
            
            # Fast filter: MUST loosely match title regex OR be the actual antigravity executable
            if not broad_title_pattern.search(title) and not is_antigravity_process:
                return True
                
            # STRONG EXCLUSION: Never attach to ForgeFlow dashboard in web browsers
            is_browser = proc_name in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe")
            if is_browser and ("forgeflow" in title.lower() or "localhost" in title.lower() or "chrome is being controlled" in title.lower()):
                diagnostics.append(f"- Ignored unsafe web browser window: '{title}' (Process: {proc_name}) - Matches ForgeFlow Dashboard.")
                return True
            
            # Explicitly reject windows that are literally just "ForgeFlow" without Antigravity
            if not is_antigravity_process and "antigravity" not in title.lower() and "forgeflow" in title.lower():
                diagnostics.append(f"- Ignored unsafe window: '{title}' (Process: {proc_name}) - Missing Antigravity in title.")
                return True
                
            score = 0
            
            # Signal 1: Process Name / Path
            if is_antigravity_process:
                score += 10
            elif proc_name in ("electron.exe", "chrome.exe", "msedge.exe"):
                score += 2
                
            # Signal 2: Window Title
            if title_pattern.match(title):
                score += 10
            elif broad_title_pattern.search(title):
                score += 5
                
            if score >= 5: # Threshold for viable candidate
                candidates.append({
                    "hwnd": int(hwnd),
                    "title": title,
                    "process": proc_name,
                    "score": score
                })
                
            return True

        EnumWindows(EnumWindowsProc(foreach_window), 0)
        
        if not candidates:
            diag_str = "Matching Criteria Used:\\n"
            diag_str += f"- Title must broadly match: {self.app_title_regex} OR process must be Antigravity\\n"
            diag_str += "- Must not be the ForgeFlow dashboard.\\n\\n"
            diag_str += "Result: No windows found matching these criteria.\\n"
            if diagnostics:
                diag_str += "Ignored:\\n" + "\\n".join(diagnostics)
            return None, diag_str
            
        # Sort by highest score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        
        if best["score"] < 5:
            diag_str = "Found candidates, but confidence was too low:\\n"
            for c in candidates:
                diag_str += f"- '{c['title']}' ({c['process']}) - Score: {c['score']}\\n"
            return None, diag_str
            
        return best, f"Found target: '{best['title']}' (Process: {best['process']})"

    def connect(self):
        """Attempts to locate the application window and bring it to the foreground."""
        try:
            logger.info("RPA: Searching for robust window match...")
            best_window, diagnostic = self._find_robust_antigravity_window()
            
            if not best_window:
                raise RPAEngineError("Antigravity application not detected", diagnostic=diagnostic)
                
            hwnd = best_window["hwnd"]
            
            # The diagnostic message contains the success information for the caller
            self.last_diagnostic = diagnostic
            
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
        except RPAEngineError:
            raise
        except Exception as e:
            logger.error(f"RPA Connection Error: {e}")
            raise RPAEngineError("An unexpected error occurred during RPA connection", diagnostic=str(e))

    def paste_text(self, text: str):
        """Pastes text directly from the clipboard to avoid slow keyboard typing."""
        if not self.main_window:
            raise RPAEngineError("Not connected to any application")
            
        logger.debug("RPA: Pasting text via clipboard")
        old_clipboard = pyperclip.paste()
        try:
            pyperclip.copy(text)
            time.sleep(0.1)
            send_keys('^v')
            time.sleep(0.1)
        finally:
            pass

    def send_keystrokes(self, keys: str):
        """Sends key strokes to the active window."""
        send_keys(keys)
        time.sleep(0.1)

    def read_clipboard(self) -> str:
        """Reads current text from the clipboard."""
        return pyperclip.paste()
        
    def wait_for_ui_ready(self, timeout_secs: int = 120, check_interval: float = 2.0):
        pass
