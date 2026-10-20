/**
 * Generate TypeScript types + endpoint metadata from the backend OpenAPI spec.
 *
 * Usage:
 *   node scripts/generate-api-types.mjs [openapi-url-or-path]
 *
 * Defaults to $BACKEND_URL/openapi.json (e.g. http://localhost:8000/openapi.json).
 * Writes src/lib/api-schema.d.ts. If the backend is unreachable it exits non-zero
 * so CI can fail loudly instead of silently drifting from the real contract.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const outFile = path.resolve(__dirname, '../src/lib/api-schema.d.ts')

const input = process.argv[2] || process.env.BACKEND_URL
  ? `${process.env.BACKEND_URL.replace(/\/$/, '')}/openapi.json`
  : 'http://localhost:8000/openapi.json'

console.log(`Generating API types from: ${input}`)
console.log(`Output: ${outFile}`)

try {
  const stdout = execFileSync(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['openapi-typescript', input, '--output', outFile, '--alphabetize'],
    { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] },
  )
  console.log(stdout)
  console.log('API types generated successfully.')
} catch (err) {
  console.error('Failed to generate API types from backend OpenAPI spec.')
  console.error('Is the backend running? (docker compose up) or pass a URL/path explicitly.')
  console.error(String(err))
  process.exit(1)
}
