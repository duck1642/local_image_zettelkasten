use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_log::Builder::default().build())
    .setup(|app| {
      let shell = app.shell();
      let sidecar_command = shell.sidecar("liz-api").unwrap();
      let (mut _rx, _child) = sidecar_command
        .spawn()
        .expect("Failed to spawn sidecar");

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
