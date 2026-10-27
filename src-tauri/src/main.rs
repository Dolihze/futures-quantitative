// Prevents additional console window on Windows in release
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::sync::Mutex;
use tauri::{Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// 管理 Python sidecar 子进程
struct SidecarProcess(Mutex<Option<CommandChild>>);

/// Windows：把当前进程放入 Job Object（KILL_ON_JOB_CLOSE）。
/// 之后派生的 sidecar（含 PyInstaller onefile 的 bootloader 及其 Python 子进程）会继承该 Job，
/// 应用无论是正常退出、被 `tauri dev` 重编译杀掉还是崩溃，系统都会一并终止它们，
/// 避免残留的 python-backend.exe 占用 5000 端口或锁住 target/debug 下的 exe（导致 PermissionDenied）。
#[cfg(windows)]
fn bind_children_to_app_lifetime() {
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::GetCurrentProcess;

    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            eprintln!("[Backend] 创建 Job Object 失败");
            return;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let ok = SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const _,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        if ok == 0 || AssignProcessToJobObject(job, GetCurrentProcess()) == 0 {
            eprintln!("[Backend] 设置 Job Object 失败（可能已处于其它 Job 中）");
            return;
        }
        // 故意不关闭 job 句柄：进程退出时句柄由系统关闭，从而触发 KILL_ON_JOB_CLOSE
    }
}

#[cfg(not(windows))]
fn bind_children_to_app_lifetime() {}

/// 打开开发者工具
#[tauri::command]
fn open_devtools(window: tauri::WebviewWindow) {
    window.open_devtools();
}

/// 关闭开发者工具
#[tauri::command]
fn close_devtools(window: tauri::WebviewWindow) {
    window.close_devtools();
}

/// 切换开发者工具
#[tauri::command]
fn toggle_devtools(window: tauri::WebviewWindow) {
    if window.is_devtools_open() {
        window.close_devtools();
    } else {
        window.open_devtools();
    }
}

fn main() {
    bind_children_to_app_lifetime();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarProcess(Mutex::new(None)))
        .setup(|app| {
            println!("[Backend] 正在启动 Python sidecar...");

            let sidecar_command = app
                .shell()
                .sidecar("python-backend")
                .expect("Failed to create sidecar command");

            let (mut rx, child) = sidecar_command
                .spawn()
                .expect("Failed to spawn Python sidecar");

            // 保存子进程引用，退出时用于清理
            let process_state: State<SidecarProcess> = app.state();
            *process_state.0.lock().unwrap() = Some(child);

            println!("[Backend] Python sidecar 已启动");

            // 监听 sidecar 输出
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[Backend STDOUT] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[Backend STDERR] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Error(err) => {
                            eprintln!("[Backend ERROR] {}", err);
                        }
                        CommandEvent::Terminated(payload) => {
                            println!("[Backend] Sidecar 进程终止: {:?}", payload);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            // 等待 Flask 监听 5000 端口（PyInstaller onefile 首次解压较慢），
            // 避免前端在后端就绪前发起请求导致 ECONNREFUSED
            let addr: std::net::SocketAddr = "127.0.0.1:5000".parse().unwrap();
            let mut ready = false;
            for _ in 0..300 {
                if std::net::TcpStream::connect_timeout(
                    &addr,
                    std::time::Duration::from_millis(200),
                )
                .is_ok()
                {
                    ready = true;
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            if ready {
                println!("[Backend] Flask 服务已就绪 (127.0.0.1:5000)");
            } else {
                eprintln!("[Backend] 等待 Flask 服务超时(30s)，请检查 sidecar 日志");
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            open_devtools,
            close_devtools,
            toggle_devtools
        ])
        .build(tauri::generate_context!())
        .expect("Error while building Tauri application")
        .run(|app_handle, event| {
            // 应用退出时终止 sidecar，避免残留 python-backend 进程占用 5000 端口
            if let tauri::RunEvent::Exit = event {
                let state: State<SidecarProcess> = app_handle.state();
                let child = state.0.lock().unwrap().take();
                if let Some(child) = child {
                    let _ = child.kill();
                }
            }
        });
}
