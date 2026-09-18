import re

with open("app/dashboard/app.css", "r", encoding="utf-8") as f:
    css = f.read()

icon_css = """
/* THEME ICON COLORS */
.theme-icon { transition: color 0.3s, opacity 0.3s, text-shadow 0.3s; font-size: 14px; }
.theme-sun { color: #E8832A; opacity: 1; text-shadow: 0 0 6px rgba(232, 131, 42, 0.6); }
.theme-moon { color: var(--text-secondary); opacity: 0.4; }

[data-theme="dark"] .theme-sun { color: var(--text-secondary); opacity: 0.4; text-shadow: none; }
[data-theme="dark"] .theme-moon { color: #A0C4FF; opacity: 1; text-shadow: 0 0 8px rgba(160, 196, 255, 0.8); }
"""

if "/* THEME ICON COLORS */" not in css:
    css += "\n" + icon_css.strip() + "\n"

with open("app/dashboard/app.css", "w", encoding="utf-8") as f:
    f.write(css)
