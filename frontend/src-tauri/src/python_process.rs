use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

pub struct PythonProcessManager {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl PythonProcessManager {
    pub fn start() -> Result<Self, String> {
        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..");

        let python = project_root.join("python/.venv/bin/python");

        let mut child = Command::new(python)
            .args(["-m", "bmis_desktop.main"])
            .current_dir(project_root.join("python"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| format!("Failed to start Python backend: {error}"))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Failed to open Python stdin".to_string())?;

        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Failed to open Python stdout".to_string())?;

        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        })
    }

    #[cfg(test)]
    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    pub fn send_request(&mut self, request: &str) -> Result<String, String> {
        writeln!(self.stdin, "{request}")
            .map_err(|error| format!("Failed to send request to Python: {error}"))?;

        self.stdin
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
        if let Err(error) = self.child.kill() {
            eprintln!("Failed to kill Python backend: {error}");
        }

        if let Err(error) = self.child.wait() {
            eprintln!("Failed to wait for Python backend: {error}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_python_backend() {
        let _manager = PythonProcessManager::start().expect("Python backend should start");
    }

    #[test]
    fn sends_ping_request() {
        let mut manager =
            PythonProcessManager::start().expect("Python backend should start");

        let response = manager
            .send_request(r#"{"command":"ping"}"#)
            .expect("Python should return a response");

        assert!(response.contains(r#""status": true"#));
        assert!(response.contains("BMis python backend is running"));
    }

    #[test]
    fn supports_multiple_requests_on_same_process() {
        let mut manager =
            PythonProcessManager::start().expect("Python backend should start");

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
        let mut manager =
            PythonProcessManager::start().expect("Python backend should start");

        let response = manager
            .send_request(r#"{"command":"unknown"}"#)
            .expect("Python should return a response");

        println!("Python response: {response}");

        assert!(response.contains(r#""status": false"#));
        assert!(response.contains("Invalid command: unknown"));
    }

    #[test]
    fn keeps_same_process_for_multiple_requests() {
        let mut manager =
            PythonProcessManager::start().expect("Python backend should start");

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
}