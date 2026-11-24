// Prevents additional console window on Windows in release
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::io::{BufRead, BufReader};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Emitter, Manager, State};

/// 后端监听地址与端口环境变量（与 backend/config.py 保持一致）
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT_ENV: &str = "BACKEND_PORT";
/// 开发模式固定端口：Vite 代理无法得知 Rust 随机选的端口，所以 debug 构建沿用该端口
const DEV_BACKEND_PORT: u16 = 5000;
/// 等待后端就绪的最长时间。onedir 不再需要每次解压，正常几秒内就绪
const READY_TIMEOUT: Duration = Duration::from_secs(60);
/// 前端据此事件得知后端状态
const EVENT_BACKEND_READY: &str = "backend-ready";

/// 后端子进程与端口状态
struct Backend {
    child: Mutex<Option<Child>>,
    port: u16,
    ready: Mutex<bool>,
}

/// Windows：把当前进程放入 Job Object（KILL_ON_JOB_CLOSE）。
/// 之后派生的 sidecar 会继承该 Job，应用无论是正常退出、被 `tauri dev` 重编译杀掉还是崩溃，
/// 系统都会一并终止它，避免残留的 python-backend.exe 占用端口或锁住 target/debug 下的文件。
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
        }
        // 故意不关闭 job 句柄：进程退出时句柄由系统关闭，从而触发 KILL_ON_JOB_CLOSE
    }
}

#[cfg(not(windows))]
fn bind_children_to_app_lifetime() {}

/// 选择后端端口：debug 用固定端口（供 Vite 代理），release 向系统申请空闲端口。
fn pick_port() -> u16 {
    if cfg!(debug_assertions) {
        std::env::var(BACKEND_PORT_ENV)
            .ok()
            .and_then(|v| v.trim().parse().ok())
            .unwrap_or(DEV_BACKEND_PORT)
    } else {
        TcpListener::bind((BACKEND_HOST, 0))
            .and_then(|l| l.local_addr())
            .map(|a| a.port())
            .unwrap_or(DEV_BACKEND_PORT)
    }
}

/// 定位 onedir 后端可执行文件：resources/backend/python-backend[.exe]。
/// 开发模式回退到 src-tauri/backend-dist（PyInstaller 的输出目录）。
fn backend_exe(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let exe = if cfg!(windows) { "python-backend.exe" } else { "python-backend" };
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(res) = app.path().resource_dir() {
        candidates.push(res.join("backend-dist").join(exe));
    }
    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("backend-dist")
            .join(exe),
    );
    candidates
        .iter()
        .find(|p| p.is_file())
        .cloned()
        .ok_or_else(|| {
            format!(
                "未找到后端可执行文件，请先运行 `npm run backend:build`。已查找：{:?}",
                candidates
            )
        })
}

fn spawn_backend(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    let exe = backend_exe(app)?;
    let mut cmd = Command::new(&exe);
    cmd.env(BACKEND_PORT_ENV, port.to_string())
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
        .current_dir(exe.parent().unwrap_or_else(|| std::path::Path::new(".")))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn().map_err(|e| format!("启动后端失败 ({}): {}", exe.display(), e))
}

/// 把子进程输出转发到本进程日志
fn forward_output(child: &mut Child) {
    if let Some(out) = child.stdout.take() {
        std::thread::spawn(move || {
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                println!("[Backend STDOUT] {}", line);
            }
        });
    }
    if let Some(err) = child.stderr.take() {
        std::thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                eprintln!("[Backend STDERR] {}", line);
            }
        });
    }
}

/// 在后台线程轮询端口，就绪后通知前端；不阻塞窗口创建。
fn wait_ready_in_background(app: tauri::AppHandle, port: u16) {
    std::thread::spawn(move || {
        let addr: SocketAddr = format!("{}:{}", BACKEND_HOST, port).parse().unwrap();
        let start = Instant::now();
        let mut ready = false;
        while start.elapsed() < READY_TIMEOUT {
            if TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok() {
                ready = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        if ready {
            println!("[Backend] Flask 服务已就绪 ({}), 用时 {:.1}s", addr, start.elapsed().as_secs_f32());
        } else {
            eprintln!(
                "[Backend] 等待 Flask 服务超时({}s)，请检查后端日志",
                READY_TIMEOUT.as_secs()
            );
        }
        let state: State<Backend> = app.state();
        *state.ready.lock().unwrap() = ready;
        let _ = app.emit(EVENT_BACKEND_READY, ready);
    });
}

/// 前端查询后端地址。端口在 setup 前已确定，所以总能立即返回。
#[tauri::command]
fn get_backend_url(state: State<Backend>) -> String {
    format!("http://{}:{}", BACKEND_HOST, state.port)
}

/// 前端查询后端是否已就绪（用于错过 backend-ready 事件时补查）。
#[tauri::command]
fn is_backend_ready(state: State<Backend>) -> bool {
    *state.ready.lock().unwrap()
}

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

/// 把前端导出的文件内容写入用户在「另存为」对话框里选定的路径。
#[tauri::command]
fn save_file(path: String, data: Vec<u8>) -> Result<(), String> {
    std::fs::write(&path, data).map_err(|e| format!("写入文件失败: {}", e))
}

fn main() {
    bind_children_to_app_lifetime();

    let port = pick_port();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Backend {
            child: Mutex::new(None),
            port,
            ready: Mutex::new(false),
        })
        .setup(move |app| {
            println!("[Backend] 正在启动 Python 后端 (端口 {})...", port);
            let handle = app.handle().clone();
            match spawn_backend(&handle, port) {
                Ok(mut child) => {
                    forward_output(&mut child);
                    let state: State<Backend> = app.state();
                    *state.child.lock().unwrap() = Some(child);
                    wait_ready_in_background(handle, port);
                }
                Err(e) => eprintln!("[Backend] {}", e),
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            is_backend_ready,
            open_devtools,
            close_devtools,
            toggle_devtools,
            save_file
        ])
        .build(tauri::generate_context!())
        .expect("Error while building Tauri application")
        .run(|app_handle, event| {
            // 应用退出时终止后端，避免残留 python-backend 进程占用端口
            if let tauri::RunEvent::Exit = event {
                let state: State<Backend> = app_handle.state();
                let child = state.child.lock().unwrap().take();
                if let Some(mut child) = child {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
