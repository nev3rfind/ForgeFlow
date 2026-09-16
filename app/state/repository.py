import json
from typing import List, Optional
from app.models import Project, Task, TaskState, Event, Artifact
from app.state.db import Database
from datetime import datetime

class Repository:
    def __init__(self, db: Database):
        self.db = db

    def save_project(self, project: Project) -> Project:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO projects 
                (id, name, description, repository, type, test_command, build_command, lint_command, format_command, default_branch, allowed_working_directories, project_instructions, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project.id, project.name, project.description, project.repository, project.type, 
                project.test_command, project.build_command, project.lint_command, project.format_command, 
                project.default_branch, json.dumps(project.allowed_working_directories), 
                project.project_instructions, 1 if project.active else 0, project.created_at.isoformat()
            ))
            conn.commit()
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_project(dict(row))
        return None

    def get_projects(self) -> List[Project]:
        projects = []
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects ORDER BY created_at DESC')
            for row in cursor.fetchall():
                projects.append(self._row_to_project(dict(row)))
        return projects

    def delete_project(self, project_id: str) -> bool:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            task_ids = [r[0] for r in cursor.execute('SELECT id FROM tasks WHERE project_id = ?', (project_id,)).fetchall()]
            for tid in task_ids:
                cursor.execute('DELETE FROM task_events WHERE task_id = ?', (tid,))
                cursor.execute('DELETE FROM artifacts WHERE task_id = ?', (tid,))
            cursor.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_project(d: dict) -> Project:
        d['allowed_working_directories'] = json.loads(d.get('allowed_working_directories') or '[]')
        d['active'] = bool(d.get('active', 1))
        d['created_at'] = datetime.fromisoformat(d['created_at']) if d.get('created_at') else None
        return Project(**d)

    def save_task(self, task: Task) -> Task:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO tasks 
                (id, project_id, title, description, requirements, priority, status, iteration, max_iterations, created_at, started_at, updated_at, completed_at, current_agent, current_worktree, error_information)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.id, task.project_id, task.title, task.description, task.requirements, task.priority,
                task.status.value, task.iteration, task.max_iterations, 
                task.created_at.isoformat() if task.created_at else None, 
                task.started_at.isoformat() if task.started_at else None, 
                task.updated_at.isoformat() if task.updated_at else None, 
                task.completed_at.isoformat() if task.completed_at else None, 
                task.current_agent, task.current_worktree, task.error_information
            ))
            conn.commit()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d['status'] = TaskState(d['status'])
                d['created_at'] = datetime.fromisoformat(d['created_at']) if d['created_at'] else None
                d['started_at'] = datetime.fromisoformat(d['started_at']) if d['started_at'] else None
                d['updated_at'] = datetime.fromisoformat(d['updated_at']) if d['updated_at'] else None
                d['completed_at'] = datetime.fromisoformat(d['completed_at']) if d['completed_at'] else None
                return Task(**d)
        return None

    def get_tasks(self, project_id: Optional[str] = None) -> List[Task]:
        tasks = []
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute('SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC', (project_id,))
            else:
                cursor.execute('SELECT * FROM tasks ORDER BY created_at DESC')
            for row in cursor.fetchall():
                d = dict(row)
                d['status'] = TaskState(d['status'])
                d['created_at'] = datetime.fromisoformat(d['created_at']) if d['created_at'] else None
                d['started_at'] = datetime.fromisoformat(d['started_at']) if d['started_at'] else None
                d['updated_at'] = datetime.fromisoformat(d['updated_at']) if d['updated_at'] else None
                d['completed_at'] = datetime.fromisoformat(d['completed_at']) if d['completed_at'] else None
                tasks.append(Task(**d))
        return tasks

    def delete_task(self, task_id: str) -> bool:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM task_events WHERE task_id = ?', (task_id,))
            cursor.execute('DELETE FROM artifacts WHERE task_id = ?', (task_id,))
            cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def save_event(self, event: Event) -> Event:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO task_events (id, task_id, timestamp, event_type, payload)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                event.id, event.task_id, event.timestamp.isoformat(), 
                event.event_type, json.dumps(event.payload)
            ))
            conn.commit()
        return event

    def get_events(self, task_id: str) -> List[Event]:
        events = []
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM task_events WHERE task_id = ? ORDER BY timestamp ASC', (task_id,))
            for row in cursor.fetchall():
                d = dict(row)
                d['timestamp'] = datetime.fromisoformat(d['timestamp'])
                d['payload'] = json.loads(d['payload'])
                events.append(Event(**d))
        return events

    def get_all_events(self, limit: int = 200) -> List[Event]:
        events = []
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM task_events ORDER BY timestamp DESC LIMIT ?', (limit,))
            for row in cursor.fetchall():
                d = dict(row)
                d['timestamp'] = datetime.fromisoformat(d['timestamp'])
                d['payload'] = json.loads(d['payload'])
                events.append(Event(**d))
        return events

    def save_artifact(self, artifact: Artifact) -> Artifact:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM artifacts WHERE task_id = ? AND name = ?",
                (artifact.task_id, artifact.name)
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "UPDATE artifacts SET path = ?, created_at = ? WHERE id = ?",
                    (artifact.path, artifact.created_at.isoformat(), existing["id"])
                )
                artifact.id = existing["id"]
            else:
                cursor.execute('''
                    INSERT INTO artifacts (id, task_id, name, path, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    artifact.id, artifact.task_id, artifact.name, artifact.path, artifact.created_at.isoformat()
                ))
            conn.commit()
        return artifact

    def delete_artifacts(self, task_id: str) -> int:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM artifacts WHERE task_id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount

    def get_artifacts(self, task_id: str) -> List[Artifact]:
        artifacts = []
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at ASC', (task_id,))
            for row in cursor.fetchall():
                d = dict(row)
                d['created_at'] = datetime.fromisoformat(d['created_at'])
                artifacts.append(Artifact(**d))
        return artifacts

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM artifacts WHERE id = ?', (artifact_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d['created_at'] = datetime.fromisoformat(d['created_at'])
                return Artifact(**d)
        return None
