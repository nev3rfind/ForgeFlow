import re

with open("app/integrations/desktop_rpa_engine.py", "r", encoding="utf-8") as f:
    content = f.read()

new_connect = """    def connect(self):
        \"\"\"Attempts to locate the application window and bring it to the foreground.\"\"\"
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
            self.main_window = self.app.window(handle=hwnd)"""

# I need to carefully replace the existing connect method
content = re.sub(
    r'    def connect\(self\):.*?self\.main_window = self\.app\.window\(handle=hwnd\)',
    new_connect,
    content,
    flags=re.DOTALL
)

with open("app/integrations/desktop_rpa_engine.py", "w", encoding="utf-8") as f:
    f.write(content)
