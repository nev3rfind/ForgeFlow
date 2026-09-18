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


    def load_custom(self):
        import os, json
        if os.path.exists("custom_providers.json"):
            try:
                with open("custom_providers.json", "r") as f:
                    data = json.load(f)
                    for item in data:
                        self.register(ProviderInfo(**item))
            except Exception as e:
                print(f"Failed to load custom providers: {e}")

    def save_custom(self, info: ProviderInfo):
        import os, json
        custom = []
        if os.path.exists("custom_providers.json"):
            try:
                with open("custom_providers.json", "r") as f:
                    custom = json.load(f)
            except:
                pass
        
        # Remove old if replacing
        custom = [c for c in custom if c.get("id") != info.id]
        custom.append(info.model_dump())
        
        with open("custom_providers.json", "w") as f:
            json.dump(custom, f, indent=2)
        
        self.register(info)

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
    supported_roles=["orchestrator", "investigator", "coder", "tester", "qa", "reviewer"],
    models=[
        ProviderModel(id="auto", name="Auto (Let Abacus Choose)"),
        ProviderModel(id="claude-3.5-sonnet", name="Claude 3.5 Sonnet"),
        ProviderModel(id="gpt-4o", name="GPT-4o"),
        ProviderModel(id="claude-3-opus", name="Claude 3 Opus"),
        ProviderModel(id="llama-3", name="Llama 3"),
        ProviderModel(id="gemini-1.5-pro", name="Gemini 1.5 Pro")
    ]
))

provider_registry.load_custom()
