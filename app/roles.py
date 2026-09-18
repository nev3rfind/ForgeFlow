import json
import os
from pydantic import BaseModel
from typing import Dict, Optional

ROLE_FILE = "role_routing.json"

class RoleConfig(BaseModel):
    provider: str
    model: Optional[str] = None

class RoleRouting:
    def __init__(self):
        self.roles: Dict[str, RoleConfig] = {
            "orchestrator": RoleConfig(provider="agy"),
            "investigator": RoleConfig(provider="agy"),
            "coder": RoleConfig(provider="agy"),
            "tester": RoleConfig(provider="agy"),
            "qa": RoleConfig(provider="agy"),
            "reviewer": RoleConfig(provider="abacus")
        }
        self.load()

    def load(self):
        if os.path.exists(ROLE_FILE):
            try:
                with open(ROLE_FILE, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k in self.roles:
                            self.roles[k] = RoleConfig(**v)
            except Exception as e:
                print(f"Error loading roles: {e}")

    def save(self):
        with open(ROLE_FILE, "w") as f:
            json.dump({k: v.model_dump() for k, v in self.roles.items()}, f, indent=2)

    def update_role(self, role: str, provider: str, model: Optional[str] = None):
        if role in self.roles:
            self.roles[role] = RoleConfig(provider=provider, model=model)
            self.save()

    def get_role(self, role: str) -> RoleConfig:
        return self.roles.get(role, RoleConfig(provider="agy"))

role_router = RoleRouting()
