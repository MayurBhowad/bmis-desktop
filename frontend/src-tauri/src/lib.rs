mod python_process;

use std::sync::Mutex;

use python_process::{create_private_directory, profile_database_path, PythonProcessManager};
use tauri::Manager;

struct AppState {
    python: Mutex<PythonProcessManager>,
}

fn startup_failure(message: String) -> Box<dyn std::error::Error> {
    message.into()
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

            let app_data_dir = app.path().app_data_dir()?;
            create_private_directory(&app_data_dir).map_err(startup_failure)?;
            let python = PythonProcessManager::start(&profile_database_path(&app_data_dir))
                .map_err(startup_failure)?;

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
    let mut python = state
        .python
        .lock()
        .map_err(|_| "Failed to lock Python process".to_string())?;

    python.send_request(&request)
}
