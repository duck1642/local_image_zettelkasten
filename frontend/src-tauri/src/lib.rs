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
    formats::FileList.write_clipboard(&paths.as_slice()).map_err(|e| e.to_string())
}

#[tauri::command]
fn toggle_devtools(webview: tauri::WebviewWindow) {
    if webview.is_devtools_open() {
        webview.close_devtools();
    } else {
        webview.open_devtools();
    }
}

fn app_logs_dir() -> Option<std::path::PathBuf> {
    let data_root = std::env::var_os("LMZ_DATA_ROOT")
        .map(std::path::PathBuf::from)
        .or_else(|| std::env::var_os("USERPROFILE").map(|home| std::path::PathBuf::from(home).join(".lmz")))
        .or_else(|| std::env::var_os("HOME").map(|home| std::path::PathBuf::from(home).join(".lmz")))?;
    Some(data_root.join("app").join("logs"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let skip_sidecar = std::env::var("LMZ_SKIP_SIDECAR").ok().as_deref() == Some("1");
  let mut log_targets = vec![
      tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Stdout),
  ];
  if !skip_sidecar {
      if let Some(path) = app_logs_dir().filter(|path| path.is_dir()) {
          log_targets.push(tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Folder {
              path,
              file_name: Some("tauri".to_string()),
          }));
      }
  }

  tauri::Builder::default()
    .on_page_load(|webview, payload| {
      if matches!(payload.event(), tauri::webview::PageLoadEvent::Started) {
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
    .invoke_handler(tauri::generate_handler![copy_file_to_clipboard, toggle_devtools])
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_log::Builder::default()
        .targets(log_targets)
        .build())
    .setup(|_app| {
      #[cfg(not(dev))]
      {
        if std::env::var("LMZ_SKIP_SIDECAR").ok().as_deref() == Some("1") {
          println!("LMZ_SKIP_SIDECAR=1; skipping lmz-api sidecar spawn");
        } else {
          use tauri_plugin_shell::ShellExt;
          let shell = _app.shell();
          match shell.sidecar("lmz-api") {
            Ok(sidecar_command) => match sidecar_command.spawn() {
              Ok((mut rx, _child)) => {
                tauri::async_runtime::spawn(async move {
                  while let Some(event) = rx.recv().await {
                    match event {
                      tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                        println!("Sidecar: {}", String::from_utf8_lossy(&line));
                      }
                      tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                        eprintln!("Sidecar: {}", String::from_utf8_lossy(&line));
                      }
                      _ => {}
                    }
                  }
                });
              }
              Err(error) => {
                eprintln!("Failed to spawn lmz-api sidecar: {error}");
              }
            },
            Err(error) => {
              eprintln!("Failed to create lmz-api sidecar command: {error}");
            }
          }
        }
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
