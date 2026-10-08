import time
import pyperclip
import logging
import ctypes
from ctypes.wintypes import DWORD, MAX_PATH, HWND, LPARAM
import re
import ntpath
from pywinauto import Application
from pywinauto.keyboard import send_keys

logger = logging.getLogger(__name__)

class RPAEngineError(Exception):
    def __init__(self, message, diagnostic=""):
        super().__init__(message)
        self.diagnostic = diagnostic

class DesktopRPAEngine:
    BROWSER_PROCESS_NAMES = frozenset({
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "vivaldi.exe",
    })

    def __init__(self, app_title_regex: str, backend: str = "uia"):
        self.app_title_regex = app_title_regex
        self.backend = backend
        self.app = None
        self.main_window = None

    def _score_window_candidate(self, title: str, process_name: str, process_path: str):
        """Return (score, match reason) for a visible top-level window candidate.

        Antigravity's Electron window title is the current conversation name, so
        title matching cannot be required when its executable identity is known.
        A title match remains as a fallback for the bundled Tk mock app. Browser
        executables are always rejected, even if their tab title looks plausible.
        """
        process_exe = ntpath.basename((process_name or "").strip()).lower()
        normalized_path = (process_path or "").strip().replace("/", "\\").lower()
        image_exe = ntpath.basename(normalized_path).lower()

        if process_exe in self.BROWSER_PROCESS_NAMES or image_exe in self.BROWSER_PROCESS_NAMES:
            return None

        # Electron frequently owns Antigravity's window, while Antigravity owns
        # the install directory. This identity is reliable even when the title
        # is an arbitrary workspace or conversation name.
        if "antigravity" in normalized_path:
            return 100, "antigravity_path"

        if process_exe == "antigravity.exe" or image_exe == "antigravity.exe":
            return 100, "antigravity_executable"

        title = (title or "").strip()
        if not title:
            return None

        exact_title_pattern = re.compile(r"^(Google\s+)?Antigravity(\s+IDE)?$", re.IGNORECASE)
        if exact_title_pattern.match(title):
            return 30, "title_fallback"

        if re.search(self.app_title_regex, title, re.IGNORECASE):
            return 20, "title_fallback"

        return None

    def _get_process_info_by_hwnd(self, hwnd):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        
        pid = DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        hProcess = kernel32.OpenProcess(0x1000, False, pid)
        if not hProcess:
            hProcess = kernel32.OpenProcess(0x0410, False, pid)
            if not hProcess:
                return "", ""
                
        exe_base = ctypes.create_unicode_buffer(MAX_PATH)
        psapi.GetModuleBaseNameW(hProcess, None, exe_base, MAX_PATH)
        
        exe_path = ctypes.create_unicode_buffer(MAX_PATH)
        size = DWORD(MAX_PATH)
        kernel32.QueryFullProcessImageNameW(hProcess, 0, exe_path, ctypes.byref(size))
        
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
            match = self._score_window_candidate(title, proc_name, proc_path)
            if match:
                score, match_reason = match
                candidates.append({
                    "hwnd": int(hwnd),
                    "title": title,
                    "process": proc_name,
                    "process_path": proc_path,
                    "score": score,
                    "match_reason": match_reason,
                })
            elif "forgeflow" in title.lower():
                diagnostics.append(
                    f"- Ignored unverified ForgeFlow-title window: '{title}' "
                    f"(Process: {proc_name or 'unknown'}, Path: {proc_path or 'unknown'})."
                )
                
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
            
        return best, (
            f"Found target: '{best['title']}' "
            f"(Process: {best['process'] or 'unknown'}, "
            f"Path: {best['process_path'] or 'unknown'}, "
            f"Matched by: {best['match_reason']})"
        )

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
