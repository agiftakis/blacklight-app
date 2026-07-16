// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use std::path::PathBuf;
use std::process::Command;

// Helper: build a path to a file inside the sibling engine\ folder.
// ...\shell\src-tauri  ->  up two  ->  ...\blacklight-app  ->  engine\<file>
fn engine_file(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("engine")
        .join(name)
}

#[tauri::command]
fn run_engine() -> Result<String, String> {
    let engine_path = engine_file("blacklight_engine.py");

    let output = Command::new("python")
        .arg(&engine_path)
        .output()
        .map_err(|e| format!("Could not launch python: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Engine reported an error:\n{stderr}"));
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[tauri::command]
fn clear_userassist() -> Result<String, String> {
    let script = engine_file("userassist_clear.py");

    let output = Command::new("python")
        .arg(&script)
        .arg("--json")
        .arg("--yes")
        .output()
        .map_err(|e| format!("Could not launch python: {e}"))?;

    // The script prints a JSON result on BOTH success and handled failure
    // (e.g. backup failed), so return stdout whenever we have it.
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if !stdout.is_empty() {
        return Ok(stdout);
    }

    // No JSON at all = the script crashed before it could report. Surface stderr.
    let stderr = String::from_utf8_lossy(&output.stderr);
    Err(format!("Clear script produced no output.\n{stderr}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![run_engine, clear_userassist])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}