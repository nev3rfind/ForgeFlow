import re

with open("cli.py", "r", encoding="utf-8") as f:
    content = f.read()

new_serve_logic = """
    elif args.command == "serve":
        import socket
        import traceback

        print("Starting ForgeFlow Server...")
        
        # Pre-check 1: Is the port already in use?
        port = 8000
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) == 0:
                print(f"\\n[ERROR] Failed to start ForgeFlow.")
                print(f"Reason: Port {port} is already in use by another application.")
                print("Please stop the other application or kill the process using this port and try again.")
                sys.exit(1)

        # Pre-check 2: DB Access and Imports
        try:
            from app.state.db import Database
            from app.config import settings
            # Just instantiating Database to ensure SQLite is accessible
            db = Database(settings.database_path)
            with db._get_connection() as conn:
                pass
        except Exception as e:
            print(f"\\n[ERROR] Failed to initialize database check.")
            print(f"Reason: {str(e)}")
            sys.exit(1)

        loop_opt = "auto"
        if sys.platform == "win32":
            # Uvicorn on Windows defaults to SelectorEventLoop which does not support async subprocesses.
            # We force it to leave the default ProactorEventLoop intact.
            loop_opt = "none"

        print(f"\\nAll checks passed. Starting server on http://localhost:{port}")
        try:
            uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True, loop=loop_opt)
        except Exception as e:
            print(f"\\n[CRITICAL ERROR] The server crashed during execution:")
            print(traceback.format_exc())
            sys.exit(1)
"""

# replace the block
old_serve_logic = """
    elif args.command == "serve":
        loop_opt = "auto"
        if sys.platform == "win32":
            # Uvicorn on Windows defaults to SelectorEventLoop which does not support async subprocesses.
            # We force it to leave the default ProactorEventLoop intact.
            loop_opt = "none"
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, loop=loop_opt)
"""

if "Pre-check 1" not in content:
    # Use exact match or regex
    # Since python's replace works with exact text, let's just make sure we capture it
    # I'll use a regex for safety
    content = re.sub(
        r'elif args\.command == "serve":[\s\S]*?uvicorn\.run\([^)]+\)',
        new_serve_logic.strip(),
        content
    )

with open("cli.py", "w", encoding="utf-8") as f:
    f.write(content)
