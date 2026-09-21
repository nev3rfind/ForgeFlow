import re

with open("app/dashboard/app.js", "r", encoding="utf-8") as f:
    js = f.read()

# 1. Update updateRole
old_role = """async function updateRole(role, provider, model) {
  if (provider === "agy_desktop") {
    toast("Verifying Desktop RPA connection...", "info");
    try {
      const res = await api("/providers/test-desktop", { method: "POST" });
      if (res.status !== "success") {
        toast("RPA Connection Failed: Please open the Antigravity Desktop app first.", "err");
        render(); // Revert dropdown visually
        return;
      }
      toast("RPA Connection Verified!", "ok");
    } catch (e) {
      toast("RPA Check Error: " + e.message, "err");
      render();
      return;
    }
  }"""

new_role = """async function updateRole(role, provider, model) {
  if (provider === "agy_desktop") {
    toast("Verifying Desktop RPA connection...", "info");
    try {
      const res = await api("/providers/test-desktop", { method: "POST" });
      if (res.status !== "success") {
        openModal("RPA Connection Failed", 
          el("div", {},
            el("p", { text: "ForgeFlow could not connect to the Antigravity Desktop app. Please make sure it is open and running." }),
            el("div", { class: "mono", style: "color: var(--err); font-size: 13px; white-space: pre-wrap; background: var(--bg); padding: 12px; border: 1px solid rgba(182, 79, 79, 0.3); border-radius: 4px; overflow-y: auto; max-height: 400px; margin-top: 12px;" }, res.message + (res.details ? "\\n\\n" + res.details : ""))
          ),
          [el("button", { class: "btn primary", text: "Close", onclick: closeModal })],
          true
        );
        render(); // Revert dropdown visually
        return;
      }
      toast("RPA Connection Verified!", "ok");
    } catch (e) {
      openModal("RPA Network Error", el("p", { text: e.message }), [el("button", { class: "btn primary", text: "Close", onclick: closeModal })]);
      render();
      return;
    }
  }"""

if old_role in js:
    js = js.replace(old_role, new_role)
else:
    print("WARNING: Could not find old_role in app.js")


# 2. Update Providers Test Connection button
old_btn = """        isDesktop ? el("button", { 
          class: "btn sm ghost", 
          text: "Test Connection", 
          onclick: () => {
            toast("Testing RPA Connection...", "info");
            api("/providers/test-desktop", {method: "POST"})
              .then(res => {
                 if (res.status === "success") {
                    toast(res.message, "ok");
                 } else {
                    toast("RPA Error: " + res.message, "err");
                 }
              })
              .catch(e => toast("Network error: " + e.message, "err"));
          }
        }) : null,"""

new_btn = """        isDesktop ? el("button", { 
          class: "btn sm ghost", 
          text: "Test Connection", 
          onclick: () => {
            toast("Testing RPA Connection...", "info");
            api("/providers/test-desktop", {method: "POST"})
              .then(res => {
                 if (res.status === "success") {
                    toast(res.message, "ok");
                 } else {
                    openModal("RPA Connection Failed", 
                      el("div", {},
                        el("p", { text: "ForgeFlow could not connect to the Antigravity Desktop app. Please make sure it is open and running." }),
                        el("div", { class: "mono", style: "color: var(--err); font-size: 13px; white-space: pre-wrap; background: var(--bg); padding: 12px; border: 1px solid rgba(182, 79, 79, 0.3); border-radius: 4px; overflow-y: auto; max-height: 400px; margin-top: 12px;" }, res.message + (res.details ? "\\n\\n" + res.details : ""))
                      ),
                      [el("button", { class: "btn primary", text: "Close", onclick: closeModal })],
                      true
                    );
                 }
              })
              .catch(e => {
                  openModal("RPA Network Error", el("p", { text: e.message }), [el("button", { class: "btn primary", text: "Close", onclick: closeModal })]);
              });
          }
        }) : null,"""

if old_btn in js:
    js = js.replace(old_btn, new_btn)
else:
    print("WARNING: Could not find old_btn in app.js")

with open("app/dashboard/app.js", "w", encoding="utf-8") as f:
    f.write(js)
