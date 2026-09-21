import re

with open("app/dashboard/app.js", "r", encoding="utf-8") as f:
    js = f.read()

# 1. Fix the "Testing RPA Connection..." toast and openModal wording for the button
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

new_btn = """        isDesktop ? el("button", { 
          class: "btn sm ghost", 
          text: "Test Connection", 
          onclick: () => {
            toast("Searching for Antigravity...", "info");
            api("/providers/test-desktop", {method: "POST"})
              .then(res => {
                 if (res.status === "success") {
                    openModal("Connection successful",
                      el("div", {},
                        el("p", { text: "Searching for Antigravity..." }),
                        el("p", { text: res.details, style: "font-weight: bold; margin-top: 10px; color: var(--ok);" })
                      ),
                      [el("button", { class: "btn primary", text: "Close", onclick: () => { closeModal(); refresh(); } })]
                    );
                 } else {
                    openModal("Antigravity application not detected", 
                      el("div", {},
                        el("p", { text: "RPA Error: Failed to connect to application." }),
                        el("div", { class: "mono", style: "color: var(--err); font-size: 13px; white-space: pre-wrap; background: var(--bg); padding: 12px; border: 1px solid rgba(182, 79, 79, 0.3); border-radius: 4px; overflow-y: auto; max-height: 400px; margin-top: 12px;" }, res.details ? res.details : res.message)
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


# 2. Add green OK color to CONNECTED
old_dot = """p.status === 'Connected' ? el("div", { class: "dot" }) : null"""
new_dot = """(p.status === 'Connected' || p.status === 'CONNECTED') ? el("div", { class: "dot" }) : null"""
js = js.replace(old_dot, new_dot)

old_color = """p.status === 'Connected' ? 'var(--ok)' : 'var(--text)'"""
new_color = """(p.status === 'Connected' || p.status === 'CONNECTED') ? 'var(--ok)' : 'var(--text)'"""
js = js.replace(old_color, new_color)

with open("app/dashboard/app.js", "w", encoding="utf-8") as f:
    f.write(js)
