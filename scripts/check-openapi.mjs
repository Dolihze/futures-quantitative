// 校验入库的 openapi.json 与当前后端代码一致（供 CI / 提交前使用）。
// 后端改了 schemas.py 或路由却没重新生成时，这里会失败并提示运行 `npm run api:types`。
import { readFileSync, rmSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const committed = join(root, 'openapi.json')
const fresh = join(root, 'openapi.check.json')

try {
  const a = readFileSync(committed, 'utf8').replace(/\r\n/g, '\n')
  const b = readFileSync(fresh, 'utf8').replace(/\r\n/g, '\n')
  if (a !== b) {
    console.error('[api:check] openapi.json 与后端代码不一致，请运行 `npm run api:types` 并提交结果。')
    process.exit(1)
  }
  console.log('[api:check] openapi.json 与后端一致')
} finally {
  rmSync(fresh, { force: true })
}
