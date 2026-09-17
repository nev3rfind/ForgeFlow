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

    args = parser.parse_args()

    if args.command == "health":
        r = requests.get(f"{API_URL}/health")
        print(r.json())
    
    elif args.command == "serve":
        loop_opt = "auto"
        if sys.platform == "win32":
            # Uvicorn on Windows defaults to SelectorEventLoop which does not support async subprocesses.
            # We force it to leave the default ProactorEventLoop intact.
            loop_opt = "none"
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, loop=loop_opt)
        
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
