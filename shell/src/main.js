const { invoke } = window.__TAURI__.core;

const $ = (sel) => document.querySelector(sel);

// Return the first present, non-empty value among candidate key names.
// This keeps panels from rendering blank if a field is named slightly differently.
function pick(obj, keys, fallback = "—") {
  for (const k of keys) {
    if (obj && obj[k] !== undefined && obj[k] !== null && obj[k] !== "") {
      return obj[k];
    }
  }
  return fallback;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function panel(tag, subtitle, action) {
  const p = el("section", "panel");
  const head = el("div", "panel-head");
  head.appendChild(el("span", "panel-tag", esc(tag)));
  if (action) head.appendChild(action);
  p.appendChild(head);
  if (subtitle) p.appendChild(el("div", "panel-sub", esc(subtitle)));
  return p;
}

function gdidPanel(g) {
  const p = panel("Identity", "GDID — a hidden ID that can follow this PC across networks");
  if (!g || g.present === false) {
    p.appendChild(el("div", "empty", "No GDID found on this machine."));
    return p;
  }
  const kv = el("div", "kv");
  const rows = [
    ["Status", esc(g.present ? "PRESENT" : "absent")],
    ["Type", esc(pick(g, ["type"]))],
    ["Value", `<span class="masked">${esc(pick(g, ["value_masked", "masked", "value"]))}</span>`],
    ["Length", esc(pick(g, ["length"]))],
    ["Location", esc(pick(g, ["location"]))],
  ];
  for (const [k, v] of rows) {
    kv.appendChild(el("div", "k", esc(k)));
    kv.appendChild(el("div", "v", v));
  }
  p.appendChild(kv);
  p.appendChild(el("div", "note", "🔒 The real value stays masked and never leaves this machine."));
  return p;
}

function execPanel(title, subtitle, art, kind) {
  const entries = Array.isArray(art && art.entries) ? art.entries : [];
  const count = art && art.count !== undefined ? art.count : entries.length;

  // Only UserAssist gets a Clear button this round (safest, sandbox-proven).
  let action = null;
  if (kind === "userassist" && art && !art.access_denied) {
    action = el("button", "clear-btn", "⌫ Clear + Backup");
    action.disabled = count === 0;
    action.addEventListener("click", () => openClearDialog(count));
  }

  const p = panel(title, subtitle, action);

  if (!art) {
    p.appendChild(el("div", "empty", "No data returned."));
    return p;
  }
  if (art.access_denied) {
    p.appendChild(el("div", "warn", "⚠ Needs administrator access — re-run Blacklight as admin to see this data."));
  }
  p.appendChild(el("div", "count", `${count} ${count === 1 ? "entry" : "entries"}`));

  // BAM is intentionally READ-ONLY (no Clear button). Explain why to the user.
  if (kind === "bam") {
    p.appendChild(el("div", "readonly-note",
      "BAM is shown read-only. Windows protects this record so that only the SYSTEM account can erase it — and it clears itself automatically within about 7 days. Blacklight won't force a SYSTEM-level edit just to delete something Windows already removes on its own."));
  }

  if (!entries.length) {
    if (!art.access_denied) p.appendChild(el("div", "empty", "Nothing recorded."));
    return p;
  }

  const list = el("div", "list");
  const shown = entries.slice(0, 100);
  for (const item of shown) {
    const row = el("div", "entry");
    const name = pick(item, ["name", "path", "program", "exe"]);
    let meta;
    if (kind === "userassist") {
      meta =
        `runs: ${esc(pick(item, ["run_count", "runcount", "count"], "0"))}` +
        ` · ${esc(pick(item, ["guid_label", "category", "label"], ""))}` +
        ` · last: ${esc(pick(item, ["last_run", "last_run_utc", "last_used", "lastRun"]))}`;
    } else {
      meta =
        `user: ${esc(pick(item, ["user", "username", "sid_name", "account"]))}` +
        ` · last: ${esc(pick(item, ["last_run", "last_run_utc", "last_used", "lastRun", "time"]))}`;
    }
    row.appendChild(el("div", "entry-name", esc(name)));
    row.appendChild(el("div", "entry-meta", meta));
    list.appendChild(row);
  }
  p.appendChild(list);
  if (entries.length > shown.length) {
    p.appendChild(el("div", "note", `Showing first ${shown.length} of ${entries.length}.`));
  }
  return p;
}

// ---- Guarded Clear dialog (UserAssist) --------------------------------
// The typed-CLEAR confirmation lives here in the UI. Only after the user
// types CLEAR does the app call clear_userassist (which backs up first).
function openClearDialog(count) {
  const overlay = el("div", "modal-overlay");
  const box = el("div", "modal");

  box.appendChild(el("div", "modal-title", "Clear UserAssist history?"));

  const body = el("div", "modal-body");
  body.innerHTML =
    `This deletes <b>${esc(count)}</b> recorded app-launch entries — your own real data only.<br><br>` +
    `<b style="color:var(--green)">A full backup is saved first</b> (a .reg file in the engine's <code>backups\\</code> folder). ` +
    `To undo, double-click that file. Nothing is faked, and nothing leaves this machine.<br><br>` +
    `<span style="color:var(--dim)">Note: a cleared history can look conspicuously empty — this is privacy hygiene, not "forensic invisibility".</span>`;
  box.appendChild(body);

  box.appendChild(el("div", "modal-label", "Type <b>CLEAR</b> to confirm:"));

  const input = el("input", "modal-input");
  input.type = "text";
  input.placeholder = "CLEAR";
  input.autocomplete = "off";
  box.appendChild(input);

  const result = el("div", "modal-result");
  box.appendChild(result);

  const actions = el("div", "modal-actions");
  const cancelBtn = el("button", "btn-ghost", "Cancel");
  const clearBtn = el("button", "btn-danger", "Clear + Backup");
  clearBtn.disabled = true;
  actions.appendChild(cancelBtn);
  actions.appendChild(clearBtn);
  box.appendChild(actions);

  overlay.appendChild(box);
  document.body.appendChild(overlay);
  input.focus();

  const close = () => overlay.remove();

  // Arm the button only on an exact "CLEAR".
  input.addEventListener("input", () => {
    clearBtn.disabled = input.value.trim() !== "CLEAR";
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !clearBtn.disabled) clearBtn.click();
    if (e.key === "Escape") close();
  });
  cancelBtn.addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

  clearBtn.addEventListener("click", async () => {
    clearBtn.disabled = true;
    cancelBtn.disabled = true;
    input.disabled = true;
    clearBtn.textContent = "Working…";
    result.className = "modal-result";
    result.textContent = "Backing up, then clearing…";
    try {
      const res = JSON.parse(await invoke("clear_userassist"));
      if (res.ok) {
        result.className = "modal-result ok";
        result.innerHTML =
          `✅ Cleared ${esc(res.cleared)} entries.<br>` +
          `<span class="path">Backup: ${esc(res.backup_path)}</span>`;
        // Re-scan so the count visibly drops.
        setTimeout(() => { close(); runScan(); }, 1600);
      } else {
        result.className = "modal-result err";
        result.textContent = "⚠ " + (res.message || res.error || "Clear failed.");
        cancelBtn.disabled = false;
        cancelBtn.textContent = "Close";
      }
    } catch (err) {
      result.className = "modal-result err";
      result.textContent = "⚠ " + String(err);
      cancelBtn.disabled = false;
      cancelBtn.textContent = "Close";
    }
  });
}

function errorPanel(err) {
  const p = panel("Error", "Something went wrong running the engine");
  p.appendChild(el("div", "warn", esc(String(err))));
  p.appendChild(
    el("div", "note",
      'If this mentions "Could not launch python", your PC uses the "py" launcher instead — tell Claude to swap it.')
  );
  return p;
}

function render(data) {
  const a = (data && data.artifacts) || {};
  const when = pick(data, ["generated_utc", "generated", "timestamp"]);
  $("#status").innerHTML = `SCAN COMPLETE · <span class="dim">${esc(when)}</span>`;
  const panels = $("#panels");
  panels.innerHTML = "";
  panels.appendChild(gdidPanel(a.gdid));
  panels.appendChild(execPanel("UserAssist", "Apps you launched from the Start menu or Explorer", a.userassist, "userassist"));
  panels.appendChild(execPanel("BAM / DAM", "Background activity — programs Windows ran on your behalf", a.bam, "bam"));
}

async function runScan() {
  const btn = $("#run-btn");
  btn.disabled = true;
  btn.textContent = "SCANNING…";
  $("#status").textContent = "Running local engine…";
  $("#panels").innerHTML = "";
  try {
    const raw = await invoke("run_engine");
    render(JSON.parse(raw));
  } catch (err) {
    $("#status").textContent = "";
    $("#panels").appendChild(errorPanel(err));
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ RUN SCAN";
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("#run-btn").addEventListener("click", runScan);
});
