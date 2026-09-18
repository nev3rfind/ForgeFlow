from typing import Dict, List, Optional
from pydantic import BaseModel

class ProviderModel(BaseModel):
    id: str
    name: str

class ProviderInfo(BaseModel):
    id: str
    display_name: str
    status: str
    supported_roles: List[str]
    models: List[ProviderModel]

class ProviderRegistry:
    def __init__(self):
        self.providers: Dict[str, ProviderInfo] = {}

    def register(self, info: ProviderInfo):
        self.providers[info.id] = info

    def get_all(self) -> List[ProviderInfo]:
        return list(self.providers.values())

    def get(self, provider_id: str) -> Optional[ProviderInfo]:
        return self.providers.get(provider_id)

provider_registry = ProviderRegistry()

# Initialize with known providers
provider_registry.register(ProviderInfo(
    id="agy",
    display_name="Google Antigravity",
    status="Connected",
    supported_roles=["orchestrator", "investigator", "coder", "tester", "qa"],
    models=[
        ProviderModel(id="default", name="Default Model"),
        ProviderModel(id="flash", name="Flash (Fast)"),
        ProviderModel(id="pro", name="Pro (Complex)")
    ]
))

provider_registry.register(ProviderInfo(
    id="abacus",
    display_name="Abacus AI",
    status="Connected",
    supported_roles=["reviewer"],
    models=[
        ProviderModel(id="default", name="Default Model"),
        ProviderModel(id="claude-3.5-sonnet", name="Claude 3.5 Sonnet"),
        ProviderModel(id="gpt-4o", name="GPT-4o")
    ]
))
