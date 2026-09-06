use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![python_ping])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[tauri::command]
fn python_ping() -> Result<String, String> {
    let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..");

    let python = project_root.join("python/.venv/bin/python");

    let mut child = Command::new(python)
        .args(["-m", "bmis_desktop.main"])
        .current_dir(project_root.join("python"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start Python: {e}"))?;

    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| "Failed to open Python stdin".to_string())?;

    writeln!(stdin, r#"{{"command":"ping"}}"#)
        .map_err(|e| format!("Failed to send request to Python: {e}"))?;

    drop(stdin);

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "Failed to open Python stdout".to_string())?;

    let mut reader = BufReader::new(stdout);
    let mut response = String::new();

    reader
        .read_line(&mut response)
        .map_err(|e| format!("Failed to read Python response: {e}"))?;

    child
        .wait()
        .map_err(|e| format!("Failed to wait for Python: {e}"))?;

    Ok(response.trim().to_string())
}