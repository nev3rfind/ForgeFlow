import re

with open("app/dashboard/app.js", "r", encoding="utf-8") as f:
    js = f.read()

# Define the function
func_code = """
  async function selectMissionTask(taskId) {
    state.selectedTaskId = taskId;
    if (!taskId) {
      state.taskEvents = [];
      state.taskArtifacts = [];
      render();
      return;
    }
    try {
      const r = await Promise.all([
        api("/tasks/" + taskId + "/events").catch(() => []),
        api("/tasks/" + taskId + "/artifacts").catch(() => [])
      ]);
      state.taskEvents = r[0] || [];
      state.taskArtifacts = r[1] || [];
    } catch (_) {}
    render();
  }
"""

if "async function selectMissionTask" not in js:
    js = js.replace("/* ---------- actions ---------- */", "/* ---------- actions ---------- */\n" + func_code)

with open("app/dashboard/app.js", "w", encoding="utf-8") as f:
    f.write(js)
