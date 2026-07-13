use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

#[cfg(not(windows))]
use std::{
    fs::{self, File, OpenOptions},
    path::PathBuf,
};

const SIDECAR_PORT: u16 = 8000;
const SIDECAR_HEALTH_PATH: &str = "/api/runtime/health";
const SIDECAR_PROTOCOL_VERSION: u64 = 1;
const SIDECAR_STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
const SIDECAR_PROBE_TIMEOUT: Duration = Duration::from_millis(250);
const SIDECAR_POLL_INTERVAL: Duration = Duration::from_millis(200);

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct SidecarStatus {
    state: String,
    ready: bool,
    message: String,
    port: u16,
}

impl SidecarStatus {
    fn new(state: &str, ready: bool, message: impl Into<String>) -> Self {
        Self {
            state: state.to_string(),
            ready,
            message: message.into(),
            port: SIDECAR_PORT,
        }
    }
}

#[cfg_attr(dev, allow(dead_code))]
#[derive(Clone)]
struct SidecarState {
    child: Arc<Mutex<Option<CommandChild>>>,
    child_running: Arc<AtomicBool>,
    nonce: String,
    status: Arc<Mutex<SidecarStatus>>,
    owner: Arc<Mutex<Option<DesktopOwnerGuard>>>,
}

impl SidecarState {
    fn new(skip_sidecar: bool) -> Self {
        let status = if skip_sidecar {
            SidecarStatus::new(
                "skipped",
                true,
                "Sidecar startup was skipped; using the configured development backend.",
            )
        } else {
            SidecarStatus::new("starting", false, "Starting the LMZ backend…")
        };
        Self {
            child: Arc::new(Mutex::new(None)),
            child_running: Arc::new(AtomicBool::new(false)),
            nonce: fresh_nonce(),
            status: Arc::new(Mutex::new(status)),
            owner: Arc::new(Mutex::new(None)),
        }
    }
}

#[cfg_attr(dev, allow(dead_code))]
#[derive(Debug)]
enum OwnerError {
    AlreadyRunning,
    Failed(String),
}

impl std::fmt::Display for OwnerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::AlreadyRunning => write!(
                f,
                "another LMZ desktop instance already owns the local runtime"
            ),
            Self::Failed(message) => write!(f, "{message}"),
        }
    }
}

#[cfg(windows)]
#[cfg_attr(dev, allow(dead_code))]
#[derive(Debug)]
struct DesktopOwnerGuard {
    handle: isize,
}

#[cfg(not(windows))]
#[cfg_attr(dev, allow(dead_code))]
#[derive(Debug)]
struct DesktopOwnerGuard {
    path: PathBuf,
    _file: File,
}

#[cfg_attr(dev, allow(dead_code))]
impl DesktopOwnerGuard {
    fn acquire() -> Result<Self, OwnerError> {
        #[cfg(windows)]
        {
            use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS};
            use windows_sys::Win32::System::Threading::CreateMutexW;

            let name: Vec<u16> = "Local\\LMZ.Desktop.Owner"
                .encode_utf16()
                .chain(std::iter::once(0))
                .collect();
            let handle = unsafe { CreateMutexW(std::ptr::null(), 1, name.as_ptr()) };
            if handle.is_null() {
                return Err(OwnerError::Failed(
                    "Windows could not create the LMZ owner mutex".to_string(),
                ));
            }
            if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
                unsafe { CloseHandle(handle) };
                return Err(OwnerError::AlreadyRunning);
            }
            Ok(Self {
                handle: handle as isize,
            })
        }

        #[cfg(not(windows))]
        {
            let path = desktop_owner_lock_path()?;
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)
                    .map_err(|error| OwnerError::Failed(error.to_string()))?;
            }
            let mut file = match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(file) => file,
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    return Err(OwnerError::AlreadyRunning);
                }
                Err(error) => return Err(OwnerError::Failed(error.to_string())),
            };
            let _ = writeln!(file, "pid={}", std::process::id());
            return Ok(Self { path, _file: file });
        }
    }
}

#[cfg(windows)]
impl Drop for DesktopOwnerGuard {
    fn drop(&mut self) {
        use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
        unsafe {
            CloseHandle(self.handle as HANDLE);
        }
    }
}

#[cfg(not(windows))]
impl Drop for DesktopOwnerGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

#[cfg(not(windows))]
fn desktop_owner_lock_path() -> Result<PathBuf, OwnerError> {
    let root = std::env::var_os("LMZ_DATA_ROOT")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".lmz")))
        .ok_or_else(|| {
            OwnerError::Failed("LMZ has no usable data-home for desktop ownership".to_string())
        })?;
    Ok(root.join("app").join("desktop-owner.lock"))
}

fn fresh_nonce() -> String {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    format!("{timestamp:x}-{:x}", std::process::id())
}

fn set_status(state: &SidecarState, next: SidecarStatus) {
    if let Ok(mut status) = state.status.lock() {
        *status = next;
    }
}

fn status_snapshot(state: &SidecarState) -> SidecarStatus {
    state
        .status
        .lock()
        .map(|status| status.clone())
        .unwrap_or_else(|_| {
            SidecarStatus::new(
                "startup_failed",
                false,
                "LMZ could not read backend startup state.",
            )
        })
}

fn is_terminal_status(status: &SidecarStatus) -> bool {
    matches!(
        status.state.as_str(),
        "skipped"
            | "dev"
            | "ready"
            | "already_running"
            | "occupied_port"
            | "wrong_listener"
            | "startup_timeout"
            | "startup_failed"
            | "crashed"
            | "stopped"
    )
}

fn child_is_present(state: &SidecarState) -> bool {
    state
        .child
        .lock()
        .map(|child| child.is_some())
        .unwrap_or(false)
}

#[derive(Debug, Deserialize)]
struct ReadinessPayload {
    service: Option<String>,
    ready: Option<bool>,
    protocol_version: Option<u64>,
    nonce: Option<String>,
}

#[derive(Debug, PartialEq, Eq)]
enum ProbeResult {
    NoListener,
    Ready,
    Occupied,
    WrongIdentity,
}

fn classify_readiness_payload(payload: &ReadinessPayload, expected_nonce: &str) -> ProbeResult {
    if payload.service.as_deref() != Some("lmz-api") {
        return ProbeResult::Occupied;
    }
    if payload.ready != Some(true)
        || payload.protocol_version != Some(SIDECAR_PROTOCOL_VERSION)
        || payload.nonce.as_deref() != Some(expected_nonce)
    {
        return ProbeResult::WrongIdentity;
    }
    ProbeResult::Ready
}

fn status_for_probe(result: ProbeResult) -> Option<SidecarStatus> {
    match result {
        ProbeResult::Ready => Some(SidecarStatus::new("ready", true, "LMZ backend is ready.")),
        ProbeResult::Occupied => Some(SidecarStatus::new(
            "occupied_port",
            false,
            "Port 8000 is occupied by a non-LMZ listener; the backend was rejected.",
        )),
        ProbeResult::WrongIdentity => Some(SidecarStatus::new(
            "wrong_listener",
            false,
            "Port 8000 answered with a stale or different LMZ identity; the backend was rejected.",
        )),
        ProbeResult::NoListener => None,
    }
}

#[cfg_attr(dev, allow(dead_code))]
fn status_for_termination(current: &SidecarStatus, code: Option<i32>) -> Option<SidecarStatus> {
    let code = code
        .map(|value| value.to_string())
        .unwrap_or_else(|| "unknown".to_string());
    if current.state == "stopping" {
        return Some(SidecarStatus::new("stopped", false, "LMZ backend stopped."));
    }
    if current.state == "starting" {
        return Some(SidecarStatus::new(
            "startup_failed",
            false,
            format!("LMZ backend exited before it became ready (code {code})."),
        ));
    }
    if current.ready {
        return Some(SidecarStatus::new(
            "crashed",
            false,
            format!("LMZ backend exited unexpectedly (code {code})."),
        ));
    }
    None
}

fn startup_timeout_status() -> SidecarStatus {
    SidecarStatus::new(
        "startup_timeout",
        false,
        "The LMZ backend did not become ready within 30 seconds.",
    )
}

fn probe_readiness(expected_nonce: &str) -> ProbeResult {
    let address = SocketAddr::from(([127, 0, 0, 1], SIDECAR_PORT));
    let mut stream = match TcpStream::connect_timeout(&address, SIDECAR_PROBE_TIMEOUT) {
        Ok(stream) => stream,
        Err(_) => return ProbeResult::NoListener,
    };
    let _ = stream.set_read_timeout(Some(SIDECAR_PROBE_TIMEOUT));
    let _ = stream.set_write_timeout(Some(SIDECAR_PROBE_TIMEOUT));
    let request = format!(
        "GET {SIDECAR_HEALTH_PATH} HTTP/1.1\r\nHost: 127.0.0.1:{SIDECAR_PORT}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return ProbeResult::Occupied;
    }
    let mut response = Vec::new();
    if stream.read_to_end(&mut response).is_err() || response.len() > 64 * 1024 {
        return ProbeResult::Occupied;
    }
    let response = String::from_utf8_lossy(&response);
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return ProbeResult::Occupied;
    };
    if !headers.starts_with("HTTP/1.1 200") && !headers.starts_with("HTTP/1.0 200") {
        return ProbeResult::Occupied;
    }
    let Ok(payload) = serde_json::from_str::<ReadinessPayload>(body) else {
        return ProbeResult::Occupied;
    };
    classify_readiness_payload(&payload, expected_nonce)
}

fn wait_for_sidecar_ready_sync(state: &SidecarState) -> SidecarStatus {
    let initial = status_snapshot(state);
    if initial.ready || is_terminal_status(&initial) {
        return initial;
    }
    let deadline = Instant::now() + SIDECAR_STARTUP_TIMEOUT;
    loop {
        let current = status_snapshot(state);
        if current.ready || is_terminal_status(&current) {
            return current;
        }
        let probe = probe_readiness(&state.nonce);
        if let Some(next) = status_for_probe(probe) {
            if next.state != "ready" {
                stop_sidecar(state);
            }
            set_status(state, next.clone());
            return next;
        }
        if !child_is_present(state) {
            let failed = SidecarStatus::new(
                "startup_failed",
                false,
                "The LMZ backend exited before it became ready.",
            );
            set_status(state, failed.clone());
            return failed;
        }
        if Instant::now() >= deadline {
            let failed = startup_timeout_status();
            stop_sidecar(state);
            set_status(state, failed.clone());
            return failed;
        }
        thread::sleep(SIDECAR_POLL_INTERVAL);
    }
}

fn stop_sidecar(state: &SidecarState) {
    let should_wait = {
        let mut status = match state.status.lock() {
            Ok(status) => status,
            Err(_) => return,
        };
        if matches!(status.state.as_str(), "ready" | "starting") {
            *status = SidecarStatus::new("stopping", false, "Stopping the LMZ backend…");
            true
        } else {
            false
        }
    };
    let child = state.child.lock().ok().and_then(|mut child| child.take());
    if let Some(child) = child {
        let pid = child.pid();
        #[cfg(windows)]
        terminate_process_tree(pid);
        let _ = child.kill();
    }
    if should_wait {
        let deadline = Instant::now() + Duration::from_secs(5);
        while state.child_running.load(Ordering::Acquire) && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(25));
        }
        set_status(
            state,
            SidecarStatus::new("stopped", false, "LMZ backend stopped."),
        );
    }
}

#[cfg(windows)]
fn terminate_process_tree(pid: u32) {
    use std::{
        os::windows::process::CommandExt,
        process::{Command, Stdio},
    };

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let _ = Command::new("taskkill.exe")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg_attr(dev, allow(dead_code))]
fn spawn_sidecar(app: &tauri::AppHandle, state: &SidecarState) {
    use tauri_plugin_shell::process::CommandEvent;

    let command = match app.shell().sidecar("lmz-api") {
        Ok(command) => command.env("LMZ_STARTUP_NONCE", &state.nonce),
        Err(error) => {
            set_status(
                state,
                SidecarStatus::new(
                    "startup_failed",
                    false,
                    format!("Could not create LMZ backend command: {error}"),
                ),
            );
            return;
        }
    };
    let (mut events, child) = match command.spawn() {
        Ok(result) => result,
        Err(error) => {
            set_status(
                state,
                SidecarStatus::new(
                    "startup_failed",
                    false,
                    format!("Could not start LMZ backend: {error}"),
                ),
            );
            return;
        }
    };
    if let Ok(mut stored_child) = state.child.lock() {
        *stored_child = Some(child);
        state.child_running.store(true, Ordering::Release);
    }
    let event_state = state.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("Sidecar: {}", String::from_utf8_lossy(&line))
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("Sidecar: {}", String::from_utf8_lossy(&line))
                }
                CommandEvent::Error(error) => eprintln!("Sidecar error: {error}"),
                CommandEvent::Terminated(payload) => {
                    event_state.child_running.store(false, Ordering::Release);
                    if let Ok(mut child) = event_state.child.lock() {
                        *child = None;
                    }
                    let current = status_snapshot(&event_state);
                    if let Some(next) = status_for_termination(&current, payload.code) {
                        set_status(&event_state, next);
                    }
                    break;
                }
                _ => {}
            }
        }
    });
}

#[tauri::command]
fn wait_for_sidecar_ready(state: State<'_, SidecarState>) -> SidecarStatus {
    wait_for_sidecar_ready_sync(state.inner())
}

#[tauri::command]
fn copy_file_to_clipboard(path: String) -> Result<(), String> {
    use clipboard_win::{formats, Clipboard, Setter};
    let file_path = std::path::PathBuf::from(&path);
    if !file_path.exists() {
        return Err(format!("Clipboard file path does not exist: {path}"));
    }
    if !file_path.is_file() {
        return Err(format!("Clipboard path is not a file: {path}"));
    }
    let paths = vec![path];
    let _clip = Clipboard::new_attempts(10).map_err(|e| e.to_string())?;
    formats::FileList
        .write_clipboard(paths.as_slice())
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn open_devtools(webview: tauri::WebviewWindow) {
    webview.open_devtools();
}

#[cfg(windows)]
fn disable_native_browser_accelerators(webview: &tauri::Webview) -> tauri::Result<()> {
    use webview2_com::Microsoft::Web::WebView2::Win32::ICoreWebView2Settings3;
    use windows_core::Interface;

    // WebView2 consumes shortcuts such as Ctrl+Shift+I before DOM key handlers.
    // Disable its accelerator layer so LMZ's app-wide setting owns those keys.
    webview.with_webview(|platform_webview| {
        let result = unsafe {
            platform_webview
                .controller()
                .CoreWebView2()
                .and_then(|core| core.Settings())
                .and_then(|settings| settings.cast::<ICoreWebView2Settings3>())
                .and_then(|settings| settings.SetAreBrowserAcceleratorKeysEnabled(false))
        };
        if let Err(error) = result {
            eprintln!("Failed to disable native WebView2 browser accelerators: {error}");
        }
    })
}

#[tauri::command]
fn stop_sidecar_command(state: State<'_, SidecarState>) -> SidecarStatus {
    stop_sidecar(state.inner());
    status_snapshot(state.inner())
}

fn app_logs_dir() -> Option<std::path::PathBuf> {
    let data_root = std::env::var_os("LMZ_DATA_ROOT")
        .map(std::path::PathBuf::from)
        .or_else(|| {
            std::env::var_os("USERPROFILE").map(|home| std::path::PathBuf::from(home).join(".lmz"))
        })
        .or_else(|| {
            std::env::var_os("HOME").map(|home| std::path::PathBuf::from(home).join(".lmz"))
        })?;
    Some(data_root.join("app").join("logs"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let skip_sidecar = std::env::var("LMZ_SKIP_SIDECAR").ok().as_deref() == Some("1");
    let mut log_targets = vec![tauri_plugin_log::Target::new(
        tauri_plugin_log::TargetKind::Stdout,
    )];
    if !skip_sidecar {
        if let Some(path) = app_logs_dir().filter(|path| path.is_dir()) {
            log_targets.push(tauri_plugin_log::Target::new(
                tauri_plugin_log::TargetKind::Folder {
                    path,
                    file_name: Some("tauri".to_string()),
                },
            ));
        }
    }

    tauri::Builder::default()
    .manage(SidecarState::new(skip_sidecar))
    .on_page_load(|webview, payload| {
        if matches!(payload.event(), tauri::webview::PageLoadEvent::Started) {
            #[cfg(windows)]
            if let Err(error) = disable_native_browser_accelerators(webview) {
                eprintln!("Failed to schedule the native WebView2 accelerator gate: {error}");
            }
            let window = webview.window();
            let reset_layout = || -> tauri::Result<()> {
                window.set_fullscreen(false)?;
                window.unmaximize()?;
                window.set_size(tauri::LogicalSize::new(580.0, 580.0))?;
                window.set_resizable(false)?;
                window.center()?;
                Ok(())
            };
            if let Err(error) = reset_layout() {
                eprintln!("Failed to restore launcher window layout: {error}");
            }
        }
    })
    .on_window_event(|window, event| {
        if matches!(event, tauri::WindowEvent::Destroyed) {
            let state = window.app_handle().state::<SidecarState>().inner().clone();
            stop_sidecar(&state);
        }
    })
    .invoke_handler(tauri::generate_handler![copy_file_to_clipboard, open_devtools, wait_for_sidecar_ready, stop_sidecar_command])
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_log::Builder::default()
        .targets(log_targets)
        .build())
    .setup(move |app| {
        let state = app.state::<SidecarState>().inner().clone();
        #[cfg(dev)]
        {
            set_status(&state, SidecarStatus::new("dev", true, "Development backend is managed externally."));
        }
        #[cfg(not(dev))]
        {
            if skip_sidecar {
                println!("LMZ_SKIP_SIDECAR=1; skipping lmz-api sidecar spawn");
            } else {
                match DesktopOwnerGuard::acquire() {
                    Ok(owner) => {
                        if let Ok(mut stored_owner) = state.owner.lock() {
                            *stored_owner = Some(owner);
                        }
                        spawn_sidecar(app.handle(), &state);
                    }
                    Err(OwnerError::AlreadyRunning) => {
                        set_status(
                            &state,
                            SidecarStatus::new(
                                "already_running",
                                false,
                                "Another LMZ desktop instance is already running; no second backend was started.",
                            ),
                        );
                    }
                    Err(error) => {
                        set_status(
                            &state,
                            SidecarStatus::new("startup_failed", false, format!("Could not claim LMZ desktop ownership: {error}")),
                        );
                    }
                }
            }
        }
        Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application")
    .run(|app_handle: &tauri::AppHandle<tauri::Wry>, event| {
        if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
            let state = app_handle.state::<SidecarState>().inner().clone();
            stop_sidecar(&state);
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn readiness_payload_requires_exact_identity() {
        let payload = ReadinessPayload {
            service: Some("lmz-api".to_string()),
            ready: Some(true),
            protocol_version: Some(SIDECAR_PROTOCOL_VERSION),
            nonce: Some("nonce".to_string()),
        };
        assert_eq!(
            classify_readiness_payload(&payload, "nonce"),
            ProbeResult::Ready
        );
        assert_eq!(
            classify_readiness_payload(&payload, "stale"),
            ProbeResult::WrongIdentity
        );
        assert_eq!(payload.service.as_deref(), Some("lmz-api"));
        assert_eq!(payload.nonce.as_deref(), Some("nonce"));
    }

    #[test]
    fn readiness_rejects_non_lmz_listener() {
        let payload = ReadinessPayload {
            service: Some("other-service".to_string()),
            ready: Some(true),
            protocol_version: Some(SIDECAR_PROTOCOL_VERSION),
            nonce: Some("nonce".to_string()),
        };
        assert_eq!(
            classify_readiness_payload(&payload, "nonce"),
            ProbeResult::Occupied
        );
    }

    #[test]
    fn lifecycle_statuses_are_deterministic_for_failure_modes() {
        assert!(status_for_probe(ProbeResult::NoListener).is_none());
        assert_eq!(
            status_for_probe(ProbeResult::Occupied).unwrap().state,
            "occupied_port"
        );
        assert_eq!(
            status_for_probe(ProbeResult::WrongIdentity).unwrap().state,
            "wrong_listener"
        );
        assert_eq!(status_for_probe(ProbeResult::Ready).unwrap().state, "ready");
        assert_eq!(startup_timeout_status().state, "startup_timeout");

        let starting = SidecarStatus::new("starting", false, "starting");
        assert_eq!(
            status_for_termination(&starting, Some(1)).unwrap().state,
            "startup_failed"
        );
        let ready = SidecarStatus::new("ready", true, "ready");
        assert_eq!(
            status_for_termination(&ready, Some(1)).unwrap().state,
            "crashed"
        );
        let stopping = SidecarStatus::new("stopping", false, "stopping");
        assert_eq!(
            status_for_termination(&stopping, None).unwrap().state,
            "stopped"
        );
    }

    #[test]
    fn nonce_is_non_empty_and_process_scoped() {
        let first = fresh_nonce();
        let second = fresh_nonce();
        assert!(!first.is_empty());
        assert_ne!(first, second);
    }

    #[test]
    fn skipped_sidecar_is_explicitly_ready_for_external_development_backend() {
        let state = SidecarState::new(true);
        let status = status_snapshot(&state);
        assert_eq!(status.state, "skipped");
        assert!(status.ready);
    }

    #[test]
    fn shutdown_waits_for_child_termination_signal() {
        let state = SidecarState::new(false);
        set_status(&state, SidecarStatus::new("ready", true, "ready"));
        state.child_running.store(true, Ordering::Release);
        let running = Arc::clone(&state.child_running);
        let released = Arc::new(AtomicBool::new(false));
        let released_signal = Arc::clone(&released);
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(50));
            released_signal.store(true, Ordering::Release);
            running.store(false, Ordering::Release);
        });

        stop_sidecar(&state);

        assert!(released.load(Ordering::Acquire));
        assert_eq!(status_snapshot(&state).state, "stopped");
    }

    #[cfg(windows)]
    #[test]
    fn desktop_owner_rejects_a_second_claim() {
        let first = DesktopOwnerGuard::acquire().expect("first owner claim should succeed");
        assert!(matches!(
            DesktopOwnerGuard::acquire(),
            Err(OwnerError::AlreadyRunning)
        ));
        drop(first);
        assert!(DesktopOwnerGuard::acquire().is_ok());
    }
}
