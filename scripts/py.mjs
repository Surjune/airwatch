#!/usr/bin/env node
/**
 * Run a command with the backend virtual environment's Python.
 *
 * Exists because the interpreter lives at a different path per platform
 * (`Scripts/python.exe` on Windows, `bin/python` elsewhere) and because cmd.exe
 * will not resolve a relative forward-slash path at all, so a plain npm script
 * cannot name it portably.
 *
 * Usage: node scripts/py.mjs -m pytest
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const backendDir = path.join(repoRoot, 'backend');

const candidates = [
  path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
  path.join(backendDir, '.venv', 'bin', 'python'),
];

const python = candidates.find((candidate) => existsSync(candidate));

if (python === undefined) {
  console.error(
    'No backend virtual environment found.\n' +
      'Create one with:\n' +
      '  cd backend\n' +
      '  python -m venv .venv\n' +
      '  .venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows\n' +
      '  .venv/bin/python -m pip install -e ".[dev]"           # macOS / Linux',
  );
  process.exit(1);
}

const result = spawnSync(python, process.argv.slice(2), {
  cwd: backendDir,
  stdio: 'inherit',
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
