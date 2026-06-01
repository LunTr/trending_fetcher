// Hide the extra console window on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::Manager;

struct Backend(Mutex<Option<Child>>);

/// Locate kb_server.py by walking up from the cwd and the executable dir.
fn find_script() -> Option<PathBuf> {
    let mut bases: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        bases.push(cwd);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            bases.push(dir.to_path_buf());
        }
    }
    for base in bases {
        let mut dir = base;
        for _ in 0..5 {
            let candidate = dir.join("kb_server.py");
            if candidate.is_file() {
                return Some(candidate);
            }
            if !dir.pop() {
                break;
            }
        }
    }
    None
}

fn python_command(py: &str) -> Command {
    let mut cmd = Command::new(py);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd
}

/// Start the resident Python search service, trying common interpreters in order.
fn spawn_backend() -> Option<Child> {
    let script = find_script()?;
    let mut candidates: Vec<String> = Vec::new();
    if let Ok(p) = std::env::var("KB_PYTHON") {
        if !p.is_empty() {
            candidates.push(p);
        }
    }
    candidates.push("python".into());
    candidates.push("python3".into());
    candidates.push(r"E:\soft\Anaconda\python.exe".into());

    for py in candidates {
        if let Ok(child) = python_command(&py).arg(&script).spawn() {
            return Some(child);
        }
    }
    None
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            app.manage(Backend(Mutex::new(spawn_backend())));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(backend) = app.try_state::<Backend>() {
                    if let Some(mut child) = backend.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
