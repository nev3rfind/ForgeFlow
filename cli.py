import argparse
import sys
import uvicorn
import requests

API_URL = "http://localhost:8000"

def main():
    parser = argparse.ArgumentParser(description="ForgeFlow CLI")
    subparsers = parser.add_subparsers(dest="command")

    # health
    subparsers.add_parser("health")

    # serve
    subparsers.add_parser("serve")

    # project list
    project_parser = subparsers.add_parser("project")
    project_subs = project_parser.add_subparsers(dest="project_cmd")
    project_subs.add_parser("list")
    p_add = project_subs.add_parser("add")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--repo", required=True)
    p_add.add_argument("--type", required=True)
    p_add.add_argument("--test-command")

    # task list / create / start / stop
    task_parser = subparsers.add_parser("task")
    task_subs = task_parser.add_subparsers(dest="task_cmd")
    task_subs.add_parser("list")
    
    t_create = task_subs.add_parser("create")
    t_create.add_argument("--project", required=True)
    t_create.add_argument("--title", required=True)
    t_create.add_argument("--desc", required=True)
    
    t_start = task_subs.add_parser("start")
    t_start.add_argument("id")
    
    t_stop = task_subs.add_parser("stop")
    t_stop.add_argument("id")

    # reset
    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument("--force", action="store_true", help="Skip confirmation")

    args = parser.parse_args()

    if args.command == "health":
        r = requests.get(f"{API_URL}/health")
        print(r.json())
        
    elif args.command == "reset":
        import os
        import shutil
        import subprocess
        from app.config import settings
        from app.state.db import Database
        from app.state.repository import Repository
        from app.models.state import TaskState

        db = Database(settings.database_path)
        repo = Repository(db)
        
        all_tasks = repo.get_tasks()
        active_states = [
            TaskState.PENDING, TaskState.PREPARING, TaskState.INVESTIGATING,
            TaskState.ROOT_CAUSE_READY, TaskState.ROOT_CAUSE_REVIEW,
            TaskState.IMPLEMENTING, TaskState.IMPLEMENTATION_READY,
            TaskState.TESTING, TaskState.QA, TaskState.REVIEW,
            TaskState.NEEDS_CHANGES, TaskState.APPROVED
        ]
        
        active_tasks = [t for t in all_tasks if t.status in active_states]
        if active_tasks:
            print(f"Error: Cannot reset. {len(active_tasks)} tasks are currently active.")
            print("Please stop them via the dashboard or CLI before resetting.")
            sys.exit(1)

        print("This will completely reset the ForgeFlow task history.")
        print("The following will be deleted:")
        print(f" - {len(all_tasks)} task records (including all events and artifacts)")
        print(f" - All temporary worktrees in: {settings.workspace_root}")
        
        if not args.force:
            ans = input("Are you sure you want to proceed? [y/N]: ")
            if ans.lower() != 'y':
                print("Aborted.")
                sys.exit(0)

        # 1. Delete worktrees from disk safely
        if settings.workspace_root and os.path.exists(settings.workspace_root):
            for item in os.listdir(settings.workspace_root):
                item_path = os.path.join(settings.workspace_root, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                    
        # 2. Prune git worktrees in registered projects to clean up Git metadata
        projects = repo.get_projects()
        for p in projects:
            if os.path.isdir(p.repository):
                try:
                    subprocess.run(["git", "worktree", "prune"], cwd=p.repository, capture_output=True, check=False)
                except Exception:
                    pass
                    
        # 3. Delete tasks, events, artifacts
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM task_events")
            cursor.execute("DELETE FROM artifacts")
            cursor.execute("DELETE FROM tasks")
            conn.commit()
            
        print("Reset complete. ForgeFlow task history is now empty.")
    
    elif args.command == "serve":
        import socket
        import traceback

        print("Starting ForgeFlow Server...")
        
        # Pre-check 1: Is the port already in use?
        port = 8000
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) == 0:
                print("\n[ERROR] Failed to start ForgeFlow.")
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
            print("\n[ERROR] Failed to initialize database check.")
            print(f"Reason: {str(e)}")
            sys.exit(1)

        loop_opt = "auto"
        if sys.platform == "win32":
            loop_opt = "none"

        print(f"\nAll checks passed. Starting server on http://localhost:{port}")
        try:
            uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True, loop=loop_opt)
        except Exception as e:
            print("\n[CRITICAL ERROR] The server crashed during execution:")
            print(traceback.format_exc())
            sys.exit(1)
        
    elif args.command == "project":
        if args.project_cmd == "list":
            r = requests.get(f"{API_URL}/projects")
            for p in r.json():
                print(f"{p['id']} | {p['name']} | {p['repository']}")
        elif args.project_cmd == "add":
            r = requests.post(f"{API_URL}/projects", json={
                "name": args.name,
                "repository": args.repo,
                "type": args.type,
                "test_command": args.test_command
            })
            print(r.json())
            
    elif args.command == "task":
        if args.task_cmd == "list":
            r = requests.get(f"{API_URL}/tasks")
            for t in r.json():
                print(f"{t['id']} | {t['status']} | {t['title']}")
        elif args.task_cmd == "create":
            r = requests.post(f"{API_URL}/tasks", json={
                "project_id": args.project,
                "title": args.title,
                "description": args.desc
            })
            print(r.json())
        elif args.task_cmd == "start":
            r = requests.post(f"{API_URL}/tasks/{args.id}/start")
            print(r.json())
        elif args.task_cmd == "stop":
            r = requests.post(f"{API_URL}/tasks/{args.id}/stop")
            print(r.json())

if __name__ == "__main__":
    main()