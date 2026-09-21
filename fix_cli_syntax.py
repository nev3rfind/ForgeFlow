import re

with open("cli.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the broken f-strings
content = content.replace('print(f"\\n  [ERROR]', 'print(f"\\n[ERROR]')
content = content.replace('print(f"\\n', 'print(f"\\\\n')

# Actually, the simplest fix is to just write it out cleanly
new_serve_logic = """
    elif args.command == "serve":
        import socket
        import traceback

        print("Starting ForgeFlow Server...")
        
        # Pre-check 1: Is the port already in use?
        port = 8000
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) == 0:
                print("\\n[ERROR] Failed to start ForgeFlow.")
                print(f"Reason: Port {port} is already in use by another application.")
                print("Please stop the other application or kill the process using this port and try again.")
                sys.exit(1)

        # Pre-check 2: DB Access and Imports
        try:
            from app.state.db import Database
            from app.config import settings
            db = Database(settings.database_path)
            with db._get_connection() as conn:
                pass
        except Exception as e:
            print("\\n[ERROR] Failed to initialize database check.")
            print(f"Reason: {str(e)}")
            sys.exit(1)

        loop_opt = "auto"
        if sys.platform == "win32":
            loop_opt = "none"

        print(f"\\nAll checks passed. Starting server on http://localhost:{port}")
        try:
            uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True, loop=loop_opt)
        except Exception as e:
            print("\\n[CRITICAL ERROR] The server crashed during execution:")
            print(traceback.format_exc())
            sys.exit(1)
"""

# Replace anything from "elif args.command == 'serve':" up to "elif args.command == 'project':"
content = re.sub(
    r'elif args\.command == "serve":[\s\S]*?elif args\.command == "project":',
    new_serve_logic.strip() + '\\n        \\n    elif args.command == "project":',
    content
)

with open("cli.py", "w", encoding="utf-8") as f:
    f.write(content)
