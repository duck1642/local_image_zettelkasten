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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let skip_sidecar = std::env::var("LMZ_SKIP_SIDECAR").ok().as_deref() == Some("1");
  let mut log_targets = vec![
      tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Stdout),
  ];
  if !skip_sidecar {
      log_targets.push(tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Folder {
          path: std::path::PathBuf::from("../../logs"),
          file_name: Some("tauri".to_string()),
      }));
  }

  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![copy_file_to_clipboard])
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
