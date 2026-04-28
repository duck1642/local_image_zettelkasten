fn main() {
    let path = "C:\\Windows\\System32\\cmd.exe";
    let _ = clipboard_win::set_clipboard(clipboard_win::formats::FileList, vec![path]);
}