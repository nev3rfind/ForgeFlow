import sys

with open("cli.py", "r", encoding="utf-8") as f:
    content = f.read()

# I will find the exact problematic lines and replace them without regex
new_lines = []
for line in content.splitlines():
    if line.strip().startswith('print("') and line.endswith('")') == False:
        # Broken line
        continue
    if '[ERROR] Failed to start ForgeFlow.' in line:
        new_lines.append('                print("\\n[ERROR] Failed to start ForgeFlow.")')
        continue
    if '[ERROR] Failed to initialize database check.' in line:
        new_lines.append('            print("\\n[ERROR] Failed to initialize database check.")')
        continue
    if 'All checks passed.' in line:
        new_lines.append('        print(f"\\nAll checks passed. Starting server on http://localhost:{port}")')
        continue
    if '[CRITICAL ERROR]' in line:
        new_lines.append('            print("\\n[CRITICAL ERROR] The server crashed during execution:")')
        continue
    new_lines.append(line)

with open("cli.py", "w", encoding="utf-8") as f:
    f.write("\\n".join(new_lines))
