// Tauri 的 externalBin 要求 sidecar 文件名带目标三元组后缀，
// 例如 python-backend-x86_64-pc-windows-msvc.exe。
// PyInstaller 打包后调用本脚本生成带后缀的副本。
import { execSync } from 'node:child_process'
import { copyFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dir = join(root, 'src-tauri', 'sidecar')
const ext = process.platform === 'win32' ? '.exe' : ''

const rustInfo = execSync('rustc -vV').toString()
const triple = /host: (\S+)/.exec(rustInfo)?.[1]
if (!triple) {
  console.error('无法从 `rustc -vV` 获取 host 目标三元组')
  process.exit(1)
}

const src = join(dir, `python-backend${ext}`)
const dest = join(dir, `python-backend-${triple}${ext}`)
if (!existsSync(src)) {
  console.error(`未找到 ${src}，请先运行 PyInstaller 打包`)
  process.exit(1)
}
copyFileSync(src, dest)
console.log(`[sidecar] ${dest}`)
