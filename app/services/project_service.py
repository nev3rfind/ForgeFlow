from typing import List, Optional
from app.models import Project
from app.state import Repository

class ProjectService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_project(self, name: str, repository_path: str, type: str, **kwargs) -> Project:
        # Drop None values so model defaults apply instead of failing validation
        # (e.g. default_branch is a required str with a default of "main").
        clean = {k: v for k, v in kwargs.items() if v is not None}
        project = Project(
            name=name,
            repository=repository_path,
            type=type,
            **clean
        )
        return self.repo.save_project(project)

    def get_project(self, project_id: str) -> Optional[Project]:
        return self.repo.get_project(project_id)

    def list_projects(self) -> List[Project]:
        return self.repo.get_projects()

    def update_project(self, project_id: str, **kwargs) -> Optional[Project]:
        project = self.repo.get_project(project_id)
        if not project:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(project, k):
                setattr(project, k, v)
        return self.repo.save_project(project)

    def delete_project(self, project_id: str) -> bool:
        return self.repo.delete_project(project_id)
