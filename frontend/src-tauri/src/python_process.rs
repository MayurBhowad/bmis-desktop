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

    pub fn stop(&mut self) -> Result<(), String> {
        self.child
            .kill()
            .map_err(|error| format!("Failed to stop Python backend: {error}"))?;

        self.child
            .wait()
            .map_err(|error| format!("Failed to wait for Python backend: {error}"))?;

        Ok(())
    }
}