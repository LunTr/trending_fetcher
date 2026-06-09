// Hide the extra console window on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::Manager;

struct Backend(Mutex<Option<Child>>);

fn search_bases(app: &tauri::App) -> Vec<PathBuf> {
    let mut bases: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        bases.push(cwd);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            bases.push(dir.to_path_buf());
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        bases.push(resource_dir);
    }
    bases
}

/// Locate the packaged Python backend executable.
fn find_backend_exe(app: &tauri::App) -> Option<PathBuf> {
    for base in search_bases(app) {
        let mut dir = base;
        for _ in 0..5 {
            for rel in [
                "kb_server_pack/kb_server_pack.exe",
                "dist/kb_server_pack/kb_server_pack.exe",
                "_up_/_up_/dist/kb_server_pack/kb_server_pack.exe",
                "resources/kb_server_pack/kb_server_pack.exe",
                "resources/_up_/_up_/dist/kb_server_pack/kb_server_pack.exe",
            ] {
                let candidate = dir.join(rel);
                if candidate.is_file() {
                    return Some(candidate);
                }
            }
            if !dir.pop() {
                break;
            }
        }
    }
    None
}

/// Locate kb_server.py in dev checkout or packaged resources.
fn find_script(app: &tauri::App) -> Option<PathBuf> {
    for base in search_bases(app) {
        let mut dir = base;
        for _ in 0..5 {
            for rel in ["kb_server.py", "trending_fetcher/kb_server.py"] {
                let candidate = dir.join(rel);
                if candidate.is_file() {
                    return Some(candidate);
                }
            }
            if !dir.pop() {
                break;
            }
        }
    }
    None
}

fn resolve_data_dir(app: &tauri::App, backend_path: &PathBuf) -> PathBuf {
    if let Ok(dir) = std::env::var("TRENDING_FETCHER_DATA_DIR") {
        if !dir.is_empty() {
            return PathBuf::from(dir);
        }
    }

    if let Some(code_dir) = backend_path.parent() {
        if code_dir.join("API_KEY.json").is_file() || code_dir.join("kb_store").is_dir() {
            return code_dir.to_path_buf();
        }
        if let Some(parent) = code_dir.parent() {
            if parent.join("API_KEY.json").is_file() || parent.join("kb_store").is_dir() {
                return parent.to_path_buf();
            }
        }
    }

    app.path()
        .app_local_data_dir()
        .map(|dir| dir.join("data"))
        .unwrap_or_else(|_| backend_path.parent().map(PathBuf::from).unwrap_or_else(|| PathBuf::from(".")))
}

fn hidden_command(program: &PathBuf) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd
}

/// Start the resident Python search service, trying common interpreters in order.
fn spawn_backend(app: &tauri::App) -> Option<Child> {
    if let Some(backend_exe) = find_backend_exe(app) {
        let data_dir = resolve_data_dir(app, &backend_exe);
        let api_key = std::env::var("TRENDING_FETCHER_API_KEY")
            .map(PathBuf::from)
            .unwrap_or_else(|_| data_dir.join("API_KEY.json"));
        let _ = std::fs::create_dir_all(&data_dir);

        let mut cmd = hidden_command(&backend_exe);
        cmd.current_dir(&data_dir)
            .env("PYTHONUNBUFFERED", "1")
            .env("TRENDING_FETCHER_CODE_DIR", backend_exe.parent().unwrap_or(&data_dir))
            .env("TRENDING_FETCHER_DATA_DIR", &data_dir)
            .env("TRENDING_FETCHER_API_KEY", &api_key);
        if let Ok(child) = cmd.spawn() {
            return Some(child);
        }
    }

    let script = find_script(app)?;
    let data_dir = resolve_data_dir(app, &script);
    let code_dir = script.parent().map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let api_key = std::env::var("TRENDING_FETCHER_API_KEY")
        .map(PathBuf::from)
        .unwrap_or_else(|_| data_dir.join("API_KEY.json"));
    let _ = std::fs::create_dir_all(&data_dir);

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
        let py_path = PathBuf::from(py);
        let mut cmd = hidden_command(&py_path);
        cmd.arg(&script)
            .current_dir(&data_dir)
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .env("PYTHONUNBUFFERED", "1")
            .env("TRENDING_FETCHER_CODE_DIR", &code_dir)
            .env("TRENDING_FETCHER_DATA_DIR", &data_dir)
            .env("TRENDING_FETCHER_API_KEY", &api_key);
        if let Ok(child) = cmd.spawn() {
            return Some(child);
        }
    }
    None
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            app.manage(Backend(Mutex::new(spawn_backend(app))));
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
