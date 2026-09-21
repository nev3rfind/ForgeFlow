import re

with open("app/dashboard/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Add cache busters
html = html.replace('src="app.js?v=2"', 'src="app.js?v=3"')

with open("app/dashboard/index.html", "w", encoding="utf-8") as f:
    f.write(html)
