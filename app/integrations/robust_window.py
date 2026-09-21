import ctypes
from ctypes.wintypes import DWORD, HANDLE, MAX_PATH
import re
import logging

logger = logging.getLogger(__name__)

def find_robust_antigravity_window():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowText = user32.GetWindowTextW
    GetWindowTextLength = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible

    candidates = []
    
    title_pattern = re.compile(r'^(Google\s+)?Antigravity(\s+IDE)?$', re.IGNORECASE)
    broad_title_pattern = re.compile(r'Antigravity', re.IGNORECASE)

    def get_process_name_by_hwnd(hwnd):
        pid = DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hProcess = kernel32.OpenProcess(0x0410, False, pid)
        if not hProcess:
            return ""
        exe_name = ctypes.create_unicode_buffer(MAX_PATH)
        psapi.GetModuleBaseNameW(hProcess, None, exe_name, MAX_PATH)
        kernel32.CloseHandle(hProcess)
        return exe_name.value.lower()

    def foreach_window(hwnd, lParam):
        if not IsWindowVisible(hwnd):
            return True
            
        length = GetWindowTextLength(hwnd)
        if not (0 < length < 10000):
            return True
            
        buff = ctypes.create_unicode_buffer(length + 1)
        GetWindowText(hwnd, buff, length + 1)
        title = buff.value.strip()
        
        proc_name = get_process_name_by_hwnd(hwnd)
        
        # STRONG EXCLUSION: Never attach to ForgeFlow dashboard or browser automation banners
        if "forgeflow" in title.lower() or "localhost" in title.lower() or "chrome is being controlled" in title.lower():
            return True
            
        score = 0
        
        # Signal 1: Process Name
        if proc_name == "antigravity.exe":
            score += 10
        elif proc_name in ("electron.exe", "chrome.exe", "msedge.exe"):
            score += 2 # Possible container
            
        # Signal 2: Window Title (Exact matches are highly scored)
        if title_pattern.match(title):
            score += 10
        elif broad_title_pattern.search(title):
            score += 5
            
        if score >= 5: # Threshold for viable candidate
            candidates.append({
                "hwnd": hwnd,
                "title": title,
                "process": proc_name,
                "score": score
            })
            
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if not candidates:
        return None, "No windows found matching Antigravity criteria."
        
    # Sort by highest score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    
    if best["score"] < 5:
        return None, "Candidates found, but confidence score too low."
        
    return best, "Found"

