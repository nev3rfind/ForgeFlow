import re

with open("app/integrations/desktop_rpa_engine.py", "r", encoding="utf-8") as f:
    content = f.read()

old_connect = """            # Connect to the process using the first found element
            pid = elements[0].process_id
            self.app = Application(backend=self.backend).connect(process=pid)"""

new_connect = """            # Connect directly via the window handle to avoid PID integer-size overflow bugs on 64-bit Windows
            hwnd = elements[0].handle
            self.app = Application(backend=self.backend).connect(handle=hwnd)"""

if old_connect in content:
    content = content.replace(old_connect, new_connect)
else:
    print("WARNING: Could not find target connect string in desktop_rpa_engine.py")

with open("app/integrations/desktop_rpa_engine.py", "w", encoding="utf-8") as f:
    f.write(content)
