mod python_process;

use std::sync::Mutex;

use python_process::PythonProcessManager;
use tauri::Manager;

struct AppState {
    python: Mutex<PythonProcessManager>,
}

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

            let python = PythonProcessManager::start()
                .expect("Failed to start Python backend");

            app.manage(AppState {
                python: Mutex::new(python),
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![python_request])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[tauri::command]
fn python_request(state: tauri::State<'_, AppState>, request: String) -> Result<String, String> {
    let request = r#"{"command":"ping"}"#;

    let mut python = state
        .python
        .lock()
        .map_err(|_| "Failed to lock Python process".to_string())?;

    python.send_request(&request)
}