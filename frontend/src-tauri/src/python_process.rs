use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStderr, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

const PROFILE_DATABASE_ENV: &str = "BMIS_PROFILE_DATABASE";
const PROFILE_DATABASE_FILE: &str = "connection-profiles.sqlite";
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);
const SHUTDOWN_POLL_INTERVAL: Duration = Duration::from_millis(20);

struct StderrCapture {
    startup_complete: AtomicBool,
    text: Mutex<String>,
}

pub struct PythonProcessManager {
    child: Child,
    stdin: Option<ChildStdin>,
    stdout: BufReader<ChildStdout>,
    stderr_thread: Option<JoinHandle<()>>,
    stderr_capture: Arc<StderrCapture>,
    reaped: bool,
}

impl PythonProcessManager {
    pub fn start(database_path: &Path) -> Result<Self, String> {
        validate_database_path(database_path)?;

        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let python = project_root.join("python/.venv/bin/python");

        let mut child = Command::new(python)
            .args(["-m", "bmis_desktop.main"])
            .current_dir(project_root.join("python"))
            .env(PROFILE_DATABASE_ENV, database_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("Failed to start Python backend: {error}"))?;

        let stdin = match child.stdin.take() {
            Some(stdin) => stdin,
            None => return fail_start(child, None, "Failed to open Python stdin"),
        };
        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => return fail_start(child, Some(stdin), "Failed to open Python stdout"),
        };
        let stderr = match child.stderr.take() {
            Some(stderr) => stderr,
            None => {
                drop(stdout);
                return fail_start(child, Some(stdin), "Failed to open Python stderr");
            }
        };

        let stderr_capture = Arc::new(StderrCapture {
            startup_complete: AtomicBool::new(false),
            text: Mutex::new(String::new()),
        });
        let stderr_thread = thread::spawn({
            let capture = Arc::clone(&stderr_capture);
            move || forward_stderr(stderr, capture)
        });

        let mut manager = Self {
            child,
            stdin: Some(stdin),
            stdout: BufReader::new(stdout),
            stderr_thread: Some(stderr_thread),
            stderr_capture,
            reaped: false,
        };

        if manager.confirm_started().is_err() {
            return Err(manager.collect_startup_failure());
        }
        manager
            .stderr_capture
            .startup_complete
            .store(true, Ordering::Relaxed);
        Ok(manager)
    }

    fn confirm_started(&mut self) -> Result<(), String> {
        let response = self.send_request(r#"{"command":"ping"}"#)?;
        if !response.contains(r#""status": true"#) {
            return Err("Failed to initialize profile storage".to_string());
        }
        Ok(())
    }

    fn collect_startup_failure(&mut self) -> String {
        self.shutdown();
        let text = match self.stderr_capture.text.lock() {
            Ok(value) => value.clone(),
            Err(poisoned) => poisoned.into_inner().clone(),
        };
        public_startup_error(&text)
    }

    fn shutdown(&mut self) {
        if self.reaped {
            return;
        }
        // Closing stdin ends the JSON Lines loop so the child exits and runs its
        // session cleanup. The wait is bounded so a stuck backend cannot block
        // application shutdown; a child that is still alive is then terminated.
        reap_child(&mut self.child, &mut self.stdin, GRACEFUL_SHUTDOWN_TIMEOUT);
        if let Some(handle) = self.stderr_thread.take() {
            let _ = handle.join();
        }
        self.reaped = true;
    }

    #[cfg(test)]
    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    pub fn send_request(&mut self, request: &str) -> Result<String, String> {
        let Some(stdin) = self.stdin.as_mut() else {
            return Err("Python stdin is closed".to_string());
        };
        writeln!(stdin, "{request}")
            .map_err(|error| format!("Failed to send request to Python: {error}"))?;

        stdin
            .flush()
            .map_err(|error| format!("Failed to flush Python stdin: {error}"))?;

        let mut response = String::new();

        self.stdout
            .read_line(&mut response)
            .map_err(|error| format!("Failed to read Python response: {error}"))?;

        if response.is_empty() {
            return Err("Python backend closed the connection".to_string());
        }

        Ok(response.trim().to_string())
    }
}

impl Drop for PythonProcessManager {
    fn drop(&mut self) {
        self.shutdown();
    }
}

pub(crate) fn profile_database_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join(PROFILE_DATABASE_FILE)
}

pub(crate) fn create_private_directory(path: &Path) -> Result<(), String> {
    if path.as_os_str().is_empty() {
        return Err("Application data directory is empty".to_string());
    }

    if let Some(metadata) = symlink_metadata(path)? {
        reject_unsafe_directory(&metadata)?;
    }

    std::fs::create_dir_all(path).map_err(|error| {
        format!(
            "Failed to create application data directory: {}",
            error.kind()
        )
    })?;

    let metadata = std::fs::symlink_metadata(path).map_err(|error| {
        format!(
            "Failed to create application data directory: {}",
            error.kind()
        )
    })?;
    reject_unsafe_directory(&metadata)?;

    #[cfg(unix)]
    restrict_directory_permissions(path)?;

    Ok(())
}

fn validate_database_path(database_path: &Path) -> Result<(), String> {
    if database_path.as_os_str().is_empty() {
        return Err("Profile database path is empty".to_string());
    }
    let text = database_path.to_string_lossy();
    if text
        .chars()
        .any(|character| character == '\n' || character == '\r' || character == '\0')
    {
        return Err("Profile database path is invalid".to_string());
    }
    Ok(())
}

fn fail_start(
    mut child: Child,
    mut stdin: Option<ChildStdin>,
    message: &str,
) -> Result<PythonProcessManager, String> {
    drop(child.stdout.take());
    drop(child.stderr.take());
    reap_child(&mut child, &mut stdin, GRACEFUL_SHUTDOWN_TIMEOUT);
    Err(message.to_string())
}

fn reap_child(child: &mut Child, stdin: &mut Option<ChildStdin>, timeout: Duration) {
    // Dropping the handle closes the pipe. A missing handle means stdin is
    // already closed; both cases let a normal JSON Lines loop finish.
    drop(stdin.take());
    if child_exited_within(child, timeout) {
        return;
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn child_exited_within(child: &mut Child, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return true,
            Ok(None) => {
                if Instant::now() >= deadline {
                    return false;
                }
                let remaining = deadline.saturating_duration_since(Instant::now());
                thread::sleep(SHUTDOWN_POLL_INTERVAL.min(remaining));
            }
            // Status is unavailable. Treat that as "not exited" so the caller
            // still terminates and reaps instead of waiting forever.
            Err(_) => return false,
        }
    }
}

fn forward_stderr(stderr: ChildStderr, capture: Arc<StderrCapture>) {
    let mut reader = BufReader::new(stderr);
    let mut line = String::new();
    loop {
        line.clear();
        match reader.read_line(&mut line) {
            Ok(0) | Err(_) => break,
            Ok(_) => {
                if capture.startup_complete.load(Ordering::Relaxed) {
                    eprint!("{line}");
                    continue;
                }
                if let Ok(mut stored) = capture.text.lock() {
                    if stored.len() < 4096 {
                        stored.push_str(&line);
                    }
                }
            }
        }
    }
}

fn public_startup_error(stderr_text: &str) -> String {
    let line = stderr_text.lines().next().unwrap_or("").trim();
    if line.is_empty()
        || line.len() > 200
        || line.contains('/')
        || line.contains('\\')
        || line.contains("Traceback")
    {
        return "Failed to initialize profile storage".to_string();
    }
    format!("Failed to initialize profile storage: {line}")
}

fn symlink_metadata(path: &Path) -> Result<Option<std::fs::Metadata>, String> {
    match std::fs::symlink_metadata(path) {
        Ok(metadata) => Ok(Some(metadata)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!(
            "Failed to create application data directory: {}",
            error.kind()
        )),
    }
}

fn reject_unsafe_directory(metadata: &std::fs::Metadata) -> Result<(), String> {
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("Application data directory is unsafe".to_string());
    }
    Ok(())
}

#[cfg(unix)]
fn restrict_directory_permissions(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;

    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).map_err(|error| {
        format!(
            "Failed to set application data directory permissions: {}",
            error.kind()
        )
    })?;
    let confirmed = std::fs::symlink_metadata(path).map_err(|error| {
        format!(
            "Failed to set application data directory permissions: {}",
            error.kind()
        )
    })?;
    if confirmed.permissions().mode() & 0o077 != 0 {
        return Err("Application data directory permissions are unsafe".to_string());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicU64;

    struct TempDatabase {
        directory: PathBuf,
    }

    impl TempDatabase {
        fn new() -> Self {
            static NEXT: AtomicU64 = AtomicU64::new(0);
            let id = NEXT.fetch_add(1, Ordering::Relaxed);
            let directory = std::env::temp_dir().join(format!(
                "bmis-desktop-test-{}-{}",
                std::process::id(),
                id
            ));
            std::fs::create_dir_all(&directory).expect("temp directory should be created");
            Self { directory }
        }

        fn path(&self) -> PathBuf {
            self.directory.join(PROFILE_DATABASE_FILE)
        }
    }

    impl Drop for TempDatabase {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.directory);
        }
    }

    fn start_backend(database: &TempDatabase) -> PythonProcessManager {
        PythonProcessManager::start(&database.path()).expect("Python backend should start")
    }

    #[test]
    fn starts_python_backend() {
        let database = TempDatabase::new();
        let _manager = start_backend(&database);
    }

    #[test]
    fn sends_ping_request() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);

        let response = manager
            .send_request(r#"{"command":"ping"}"#)
            .expect("Python should return a response");

        assert!(response.contains(r#""status": true"#));
        assert!(response.contains("BMis python backend is running"));
    }

    #[test]
    fn supports_multiple_requests_on_same_process() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);

        let first_response = manager
            .send_request(r#"{"command":"ping"}"#)
            .expect("First request should succeed");

        let second_response = manager
            .send_request(r#"{"command":"ping"}"#)
            .expect("Second request should succeed");

        assert!(first_response.contains("BMis python backend is running"));
        assert!(second_response.contains("BMis python backend is running"));
    }

    #[test]
    fn forwards_unknown_command() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);

        let response = manager
            .send_request(r#"{"command":"unknown"}"#)
            .expect("Python should return a response");

        assert!(response.contains(r#""status": false"#));
        assert!(response.contains("Invalid command: unknown"));
    }

    #[test]
    fn keeps_same_process_for_multiple_requests() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);

        let first_pid = manager.pid();

        let first_response = manager
            .send_request(r#"{"command":"ping"}"#)
            .expect("First request should succeed");

        let second_pid = manager.pid();

        let second_response = manager
            .send_request(r#"{"command":"ping"}"#)
            .expect("Second request should succeed");

        let third_pid = manager.pid();

        assert_eq!(first_pid, second_pid);
        assert_eq!(second_pid, third_pid);

        assert!(first_response.contains("BMis python backend is running"));
        assert!(second_response.contains("BMis python backend is running"));
    }

    fn startup_error(database_path: &Path) -> String {
        match PythonProcessManager::start(database_path) {
            Ok(_) => panic!("Python startup should have failed"),
            Err(error) => error,
        }
    }

    #[test]
    fn rejects_an_empty_database_path() {
        assert_eq!(
            startup_error(Path::new("")),
            "Profile database path is empty"
        );
    }

    #[test]
    fn start_fails_when_profile_directory_is_missing() {
        let database = TempDatabase::new();
        let missing = database
            .directory
            .join("missing")
            .join(PROFILE_DATABASE_FILE);
        let error = startup_error(&missing);

        assert!(error.contains("Profile database directory does not exist"));
        assert!(!error.contains("bmis-desktop-test"));
        assert!(!error.contains("Traceback"));
    }

    #[test]
    fn saves_profiles_through_the_configured_database() {
        let database = TempDatabase::new();
        let profile_id = {
            let mut manager = start_backend(&database);
            let raw = manager
                .send_request(
                    r#"{"command":"create_profile","name":"Local","host":"127.0.0.1","port":6379}"#,
                )
                .expect("create should succeed");
            let response: serde_json::Value =
                serde_json::from_str(&raw).expect("create response should be JSON");
            assert_eq!(response["status"], true);
            response["profile"]["id"]
                .as_str()
                .expect("profile id")
                .to_string()
        };

        let mut manager = start_backend(&database);
        let raw = manager
            .send_request(r#"{"command":"list_profiles"}"#)
            .expect("list should succeed");
        let response: serde_json::Value =
            serde_json::from_str(&raw).expect("list response should be JSON");
        assert_eq!(response["status"], true);
        assert_eq!(response["profiles"][0]["id"], profile_id);
        assert_eq!(response["profiles"][0]["name"], "Local");
    }

    #[test]
    fn profile_requests_cannot_select_the_database_path() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);
        let other = database.directory.join("missing").join("other.sqlite");
        let request = serde_json::json!({
            "command": "create_profile",
            "name": "Local",
            "host": "127.0.0.1",
            "port": 6379,
            "database": other,
        });

        let raw = manager
            .send_request(&request.to_string())
            .expect("create should use the startup database");
        let response: serde_json::Value =
            serde_json::from_str(&raw).expect("create response should be JSON");

        assert_eq!(response["status"], true);
        assert!(database.path().is_file());
        assert!(!other.exists());
    }

    #[test]
    fn profile_database_path_uses_the_application_data_directory() {
        let app_data = Path::new("app-data");
        assert_eq!(
            profile_database_path(app_data),
            app_data.join(PROFILE_DATABASE_FILE)
        );
    }

    #[test]
    fn create_private_directory_rejects_an_empty_path() {
        let error = create_private_directory(Path::new(""))
            .expect_err("an empty directory should be rejected");
        assert_eq!(error, "Application data directory is empty");
    }

    #[cfg(unix)]
    #[test]
    fn create_private_directory_restricts_permissions() {
        use std::os::unix::fs::PermissionsExt;

        let database = TempDatabase::new();
        let path = database.directory.join("app-data");
        create_private_directory(&path).expect("directory should be created");

        let mode = std::fs::metadata(&path)
            .expect("metadata")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o700);
    }

    #[cfg(unix)]
    #[test]
    fn create_private_directory_tightens_an_existing_directory() {
        use std::os::unix::fs::PermissionsExt;

        let database = TempDatabase::new();
        let path = database.directory.join("app-data");
        std::fs::create_dir(&path).expect("directory should be created");
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))
            .expect("permissions should be set");

        create_private_directory(&path).expect("directory should be tightened");
        let mode = std::fs::metadata(&path)
            .expect("metadata")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o700);
    }

    #[cfg(unix)]
    #[test]
    fn create_private_directory_rejects_a_symlink() {
        use std::os::unix::fs::PermissionsExt;

        let database = TempDatabase::new();
        let target = database.directory.join("target");
        std::fs::create_dir(&target).expect("target directory should be created");
        std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o755))
            .expect("permissions should be set");
        let link = database.directory.join("link");
        std::os::unix::fs::symlink(&target, &link).expect("symlink should be created");

        let error = create_private_directory(&link).expect_err("symlink should be rejected");
        assert_eq!(error, "Application data directory is unsafe");
        let mode = std::fs::metadata(&target)
            .expect("metadata")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o755);
    }

    #[test]
    fn create_private_directory_rejects_a_file() {
        let database = TempDatabase::new();
        let file = database.directory.join("not-a-directory");
        std::fs::write(&file, b"x").expect("file should be created");

        let error = create_private_directory(&file).expect_err("a file should be rejected");
        assert_eq!(error, "Application data directory is unsafe");
    }

    fn python_interpreter() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../python/.venv/bin/python")
    }

    fn spawn_python_script(script: &str) -> (Child, Option<ChildStdin>) {
        let mut child = Command::new(python_interpreter())
            .arg("-c")
            .arg(script)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("Python child should start");
        let stdin = child.stdin.take();
        (child, stdin)
    }

    fn exit_status(child: &mut Child) -> std::process::ExitStatus {
        child
            .try_wait()
            .expect("child status should be readable")
            .expect("child should have exited")
    }

    #[test]
    fn shutdown_reaps_a_backend_that_exits_when_stdin_closes() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);

        manager.shutdown();

        let status = exit_status(&mut manager.child);
        assert!(status.success());
        assert!(manager.reaped);
        assert!(manager.stdin.is_none());
        assert!(manager.stderr_thread.is_none());

        manager.shutdown();
        assert!(manager.reaped);
        assert!(exit_status(&mut manager.child).success());
    }

    #[test]
    fn shutdown_is_safe_when_stdin_is_already_closed() {
        let database = TempDatabase::new();
        let mut manager = start_backend(&database);
        drop(manager.stdin.take());

        manager.shutdown();

        assert!(exit_status(&mut manager.child).success());
        manager.shutdown();
        assert!(manager.reaped);
    }

    #[test]
    fn reap_child_waits_for_a_child_that_exits_on_stdin_close() {
        let (mut child, mut stdin) = spawn_python_script("import sys; sys.stdin.read()");

        reap_child(&mut child, &mut stdin, Duration::from_secs(5));

        assert!(exit_status(&mut child).success());
        reap_child(&mut child, &mut stdin, Duration::ZERO);
        assert!(exit_status(&mut child).success());
    }

    #[test]
    fn reap_child_terminates_a_child_that_ignores_closed_stdin() {
        let (mut child, mut stdin) = spawn_python_script("import time; time.sleep(3600)");

        reap_child(&mut child, &mut stdin, Duration::ZERO);

        let status = exit_status(&mut child);
        assert!(!status.success());
        #[cfg(unix)]
        {
            use std::os::unix::process::ExitStatusExt;
            assert_eq!(status.signal(), Some(9));
        }

        reap_child(&mut child, &mut stdin, Duration::from_secs(5));
        assert!(!exit_status(&mut child).success());
    }

    #[test]
    fn reap_child_is_safe_when_the_child_has_already_exited() {
        let (mut child, mut stdin) = spawn_python_script("pass");
        let status = child.wait().expect("Python should exit");
        assert!(status.success());

        reap_child(&mut child, &mut stdin, Duration::ZERO);

        assert!(exit_status(&mut child).success());
    }

    #[test]
    fn reap_child_is_safe_when_stdin_is_already_closed() {
        let (mut child, stdin) = spawn_python_script("import time; time.sleep(3600)");
        drop(stdin);
        let mut closed = None;

        reap_child(&mut child, &mut closed, Duration::ZERO);

        assert!(!exit_status(&mut child).success());
    }

    #[test]
    fn fail_start_reaps_the_child_and_returns_the_startup_error() {
        let (child, stdin) = spawn_python_script("import sys; sys.stdin.read()");

        let error = match fail_start(child, stdin, "Failed to open Python stdout") {
            Ok(_) => panic!("startup should fail"),
            Err(error) => error,
        };

        assert_eq!(error, "Failed to open Python stdout");
    }
}
