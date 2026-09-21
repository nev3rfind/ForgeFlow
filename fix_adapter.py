import re

with open("app/integrations/agy_desktop_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

old_func = """    def is_available(self) -> bool:
        # Check if the pywinauto dependencies are loaded and windows exist
        try:
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=self.rpa.app_title_regex)
            return len(windows) > 0
        except Exception:
            return False"""

new_func = """    def is_available(self) -> bool:
        try:
            best_window, _ = self.rpa._find_robust_antigravity_window()
            return best_window is not None
        except Exception:
            return False"""

if old_func in content:
    content = content.replace(old_func, new_func)

with open("app/integrations/agy_desktop_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
