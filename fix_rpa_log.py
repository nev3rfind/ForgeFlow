import re

with open("app/main.py", "r", encoding="utf-8") as f:
    content = f.read()

old_func = """@app.post("/providers/test-desktop")
def test_desktop_connection():
    try:
        from app.integrations.desktop_rpa_engine import DesktopRPAEngine
        # Initialize engine pointing to Antigravity window
        rpa = DesktopRPAEngine(".*Antigravity.*")
        
        # Check if we can connect and focus
        rpa.connect()
        
        # Test input (just pasting to clipboard and typing, without hitting enter to keep it safe)
        rpa.paste_text("RPA Connection Test Successful!")
        
        return {"status": "success", "message": "Successfully found the Antigravity Desktop app and injected text."}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "details": traceback.format_exc()}"""

new_func = """@app.post("/providers/test-desktop")
def test_desktop_connection():
    import datetime
    log_path = "rpa_connection.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\\n[{timestamp}] --- Test Connection Attempt ---\\n")
        
        try:
            from app.integrations.desktop_rpa_engine import DesktopRPAEngine
            # Initialize engine pointing to Antigravity window
            rpa = DesktopRPAEngine(".*Antigravity.*")
            
            # Check if we can connect and focus
            rpa.connect()
            
            # Test input (just pasting to clipboard and typing, without hitting enter to keep it safe)
            msg = "RPA Connection Test Successful!"
            rpa.paste_text(msg)
            
            f.write(f"Result: SUCCESS\\nMessage: Found Antigravity app and sent text: '{msg}'\\n")
            return {"status": "success", "message": "Successfully found the Antigravity Desktop app and injected text."}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            f.write(f"Result: ERROR\\nMessage: {str(e)}\\nDetails:\\n{tb}\\n")
            return {"status": "error", "message": str(e), "details": tb}"""

if old_func in content:
    content = content.replace(old_func, new_func)
else:
    print("WARNING: Could not find target test_desktop_connection string in main.py")

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(content)
