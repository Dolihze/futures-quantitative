// 首次运行 / 换新机器时的一键准备：npm run setup
// 依次：安装前端依赖 → 安装 Python 依赖 → 打包后端 sidecar。
// 之后用 `npm run dev` 启动即可。
import { spawnSync } from 'node:child_process'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

function run(title, command, cwd = root) {
  console.log(`\n=== ${title} ===\n> ${command}`)
  const r = spawnSync(command, { cwd, stdio: 'inherit', shell: true })
  if (r.status !== 0) {
    console.error(`\n[setup] 失败：${title}（退出码 ${r.status}）`)
    process.exit(r.status ?? 1)
  }
}

run('安装前端依赖', 'npm install', join(root, 'frontend'))
// 用 `python -m pip` 而不是裸 `pip`，保证装进的是后面打包所用的同一个 Python
run('安装 Python 依赖', 'python -m pip install -r requirements.txt')
run('打包后端 sidecar', 'npm run backend:build')

console.log('\n[setup] 完成。现在可以运行：npm run dev')
