import sqlite3
import json
from typing import Optional, List, Dict, Any
from app.models.project import Project
from app.models.task import Task
from app.models.state import TaskState
from app.models.event import Event
from app.models.artifact import Artifact
from datetime import datetime
import os

class Database:
    def __init__(self, db_path: str = "forgeflow.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    repository TEXT NOT NULL,
                    type TEXT NOT NULL,
                    test_command TEXT,
                    build_command TEXT,
                    lint_command TEXT,
                    format_command TEXT,
                    default_branch TEXT,
                    allowed_working_directories TEXT,
                    project_instructions TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    requirements TEXT,
                    priority TEXT DEFAULT 'medium',
                    status TEXT NOT NULL,
                    iteration INTEGER,
                    max_iterations INTEGER,
                    created_at TIMESTAMP,
                    started_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    current_agent TEXT,
                    current_worktree TEXT,
                    error_information TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_events (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    timestamp TIMESTAMP,
                    event_type TEXT NOT NULL,
                    payload TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TIMESTAMP,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                )
            ''')
            conn.commit()

        self._migrate()

    def _migrate(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(projects)")
            pcols = {row[1] for row in cursor.fetchall()}
            if "description" not in pcols:
                cursor.execute("ALTER TABLE projects ADD COLUMN description TEXT")
            if "active" not in pcols:
                cursor.execute("ALTER TABLE projects ADD COLUMN active INTEGER DEFAULT 1")

            cursor.execute("PRAGMA table_info(tasks)")
            tcols = {row[1] for row in cursor.fetchall()}
            if "requirements" not in tcols:
                cursor.execute("ALTER TABLE tasks ADD COLUMN requirements TEXT")
            if "priority" not in tcols:
                cursor.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'medium'")

            conn.commit()
