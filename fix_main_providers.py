import re

with open("app/main.py", "r", encoding="utf-8") as f:
    content = f.read()

old_func = """@app.get("/providers")
def get_providers():
    return [p.model_dump() for p in provider_registry.get_all()]"""

new_func = """@app.get("/providers")
def get_providers():
    providers = []
    for p in provider_registry.get_all():
        dump = p.model_dump()
        if dump["id"] == "agy_desktop":
            from app.integrations.agy_desktop_adapter import AgyDesktopAdapter
            adapter = AgyDesktopAdapter()
            if adapter.is_available():
                dump["status"] = "CONNECTED"
            else:
                dump["status"] = "NOT FOUND"
        providers.append(dump)
    return providers"""

if old_func in content:
    content = content.replace(old_func, new_func)

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(content)
