// tauri dev 的 beforeDevCommand：启动前端前先清理上次异常退出遗留的本项目 Vite 进程。
// Windows 下终止 tauri/cmd 父进程不会连带结束 beforeDevCommand 子进程，
// 残留的 Vite 会占住 5173 端口（vite.config.js 使用 strictPort）导致下次启动失败。
// 只会结束“监听 5173 且命令行指向本项目 frontend 目录”的进程，不会误杀其它程序。
import { execSync, spawn } from 'node:child_process'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PORT = 5173
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const frontendDir = join(root, 'frontend')

function sh(cmd) {
  try {
    return execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  } catch {
    return ''
  }
}

function freePort() {
  if (process.platform !== 'win32') return
  const pids = sh(
    `powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort ${PORT} -State Listen -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique"`
  )
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)

  for (const pid of pids) {
    const cmdline = sh(
      `powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine"`
    ).toLowerCase()
    if (cmdline.includes('vite') && cmdline.includes(frontendDir.toLowerCase())) {
      console.log(`[dev-frontend] 结束残留的 Vite 进程 pid=${pid}（占用端口 ${PORT}）`)
      sh(`taskkill /PID ${pid} /T /F`)
    } else {
      console.error(
        `[dev-frontend] 端口 ${PORT} 被其它程序占用 (pid=${pid})，请手动释放后重试:\n  ${cmdline}`
      )
      process.exit(1)
    }
  }
}

freePort()

const child = spawn('npm run dev', {
  cwd: frontendDir,
  stdio: 'inherit',
  shell: true,
})
child.on('exit', (code) => process.exit(code ?? 0))
