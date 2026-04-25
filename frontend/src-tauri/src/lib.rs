#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_log::Builder::default()
        .targets([
            tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Stdout),
            tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Folder {
                path: std::path::PathBuf::from("../../logs"),
                file_name: Some("tauri".to_string()),
            }),
        ])
        .build())
    .setup(|_app| {
      #[cfg(not(dev))]
      {
        use tauri_plugin_shell::ShellExt;
        let shell = _app.shell();
        let sidecar_command = shell.sidecar("liz-api").unwrap();
        let (mut rx, _child) = sidecar_command
          .spawn()
          .expect("Failed to spawn sidecar");

        tauri::async_runtime::spawn(async move {
          while let Some(event) = rx.recv().await {
              if let tauri_plugin_shell::process::CommandEvent::Stdout(line) = event {
                  println!("Sidecar: {}", String::from_utf8_lossy(&line));
              }
          }
        });
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
