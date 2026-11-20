// 打包 Python 后端（PyInstaller onedir）-> src-tauri/backend-dist/
// 打包定义见 packaging/python-backend.spec；中间产物放在 .build/ 下（已 gitignore），不污染项目根目录。
import { spawnSync } from 'node:child_process'
import { existsSync, rmSync, renameSync, mkdirSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const spec = join(root, 'packaging', 'python-backend.spec')
const workDir = join(root, '.build', 'pyinstaller')
const distTmp = join(root, '.build', 'dist')
const out = join(root, 'src-tauri', 'backend-dist')

for (const dir of [workDir, distTmp, out]) rmSync(dir, { recursive: true, force: true })
mkdirSync(dirname(out), { recursive: true })

const r = spawnSync(
  'python',
  ['-m', 'PyInstaller', '--noconfirm', '--workpath', workDir, '--distpath', distTmp, spec],
  { cwd: root, stdio: 'inherit' }
)
if (r.status !== 0) {
  console.error(`[backend:build] PyInstaller 失败（退出码 ${r.status}）`)
  process.exit(r.status ?? 1)
}

// COLLECT 输出为 <distpath>/python-backend/，整体移到 src-tauri/backend-dist/
const built = join(distTmp, 'python-backend')
if (!existsSync(built)) {
  console.error(`[backend:build] 未找到输出目录：${built}`)
  process.exit(1)
}
// Windows 上刚生成的几千个文件会被杀毒软件（Defender 实时防护）、索引服务短暂占用，rename 目录时会偶发 EPERM / EBUSY，
// 过几百毫秒就好（已遇到两次，手动再移动一次都成功）。所以重试几次，而不是让整个构建在最后一步失败。
function renameWithRetry(from, to, attempts = 8, delayMs = 750) {
  for (let i = 1; ; i++) {
    try {
      renameSync(from, to)
      return
    } catch (e) {
      const transient = e && (e.code === 'EPERM' || e.code === 'EBUSY' || e.code === 'EACCES')
      if (!transient || i >= attempts) throw e
      console.warn(`[backend:build] 移动输出目录被占用（${e.code}），${delayMs}ms 后重试 ${i}/${attempts - 1}…`)
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, delayMs)   // 同步 sleep，不引入依赖
    }
  }
}
renameWithRetry(built, out)
// Tauri 编译期要求 resources 目录存在；上面清空时连占位文件一起删了，这里补回，避免它在 git 里显示为已删除
writeFileSync(join(out, '.gitkeep'), '')
rmSync(join(root, '.build'), { recursive: true, force: true })
console.log(`[backend:build] 完成：${out}`)
