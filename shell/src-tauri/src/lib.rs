// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

// Run the bundled sidecar with the given args, collect its full stdout, and
// return it. `app` is how we reach Tauri's shell plugin, which knows where the
// sidecar .exe actually lives inside the installed app (no path guessing).
async fn run_sidecar(app: &tauri::AppHandle, args: Vec<&str>) -> Result<String, String> {
    // sidecar("blacklight-engine") resolves to binaries/blacklight-engine-<triple>.exe
    let sidecar = app
        .shell()
        .sidecar("blacklight-engine")
        .map_err(|e| format!("Could not locate the engine: {e}"))?
        .args(args);

    let (mut rx, _child) = sidecar
        .spawn()
        .map_err(|e| format!("Could not launch the engine: {e}"))?;

    // The sidecar streams its output in chunks; collect stdout and stderr.
    let mut stdout = String::new();
    let mut stderr = String::new();
    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(bytes) => {
                stdout.push_str(&String::from_utf8_lossy(&bytes));
            }
            CommandEvent::Stderr(bytes) => {
                stderr.push_str(&String::from_utf8_lossy(&bytes));
            }
            _ => {}
        }
    }

    let out = stdout.trim().to_string();
    if !out.is_empty() {
        return Ok(out);
    }

    // No stdout at all = the engine crashed before it could report. Surface stderr.
    Err(format!("The engine produced no output.\n{}", stderr.trim()))
}

#[tauri::command]
async fn run_engine(app: tauri::AppHandle) -> Result<String, String> {
    // Combined artifact scan -> one JSON document (same as before, via sidecar).
    run_sidecar(&app, vec!["scan"]).await
}

#[tauri::command]
async fn clear_userassist(app: tauri::AppHandle) -> Result<String, String> {
    // Backup-first guarded clear. The dispatcher's `clear-userassist` command
    // runs the exact backup+clear path the app already expects, and prints one
    // JSON result on BOTH success and handled failure.
    run_sidecar(&app, vec!["clear-userassist"]).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![run_engine, clear_userassist])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}