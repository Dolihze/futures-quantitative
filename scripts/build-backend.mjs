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
renameSync(built, out)
// Tauri 编译期要求 resources 目录存在；上面清空时连占位文件一起删了，这里补回，避免它在 git 里显示为已删除
writeFileSync(join(out, '.gitkeep'), '')
rmSync(join(root, '.build'), { recursive: true, force: true })
console.log(`[backend:build] 完成：${out}`)
