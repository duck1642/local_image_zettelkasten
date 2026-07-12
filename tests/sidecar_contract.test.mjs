import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, '$1'), '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');

test('packaged sidecar uses one canonical fixed API base', () => {
  const api = read('frontend/src/lib/api.ts');
  const config = JSON.parse(read('frontend/src-tauri/tauri.conf.json'));
  const vite = read('frontend/vite.config.ts');
  const csp = config.app.security.csp;

  assert.match(api, /DEFAULT_API_BASE\s*=\s*['"]http:\/\/127\.0\.0\.1:8000['"]/);
  assert.match(csp, /http:\/\/127\.0\.0\.1:8000/);
  assert.doesNotMatch(csp, /localhost:8000/);
  assert.match(vite, /http:\/\/127\.0\.0\.1:8000/);
  assert.doesNotMatch(vite, /localhost:8000/);
});

test('launcher gates API calls on the native readiness command', () => {
  const api = read('frontend/src/lib/api.ts');
  const launcher = read('frontend/src/lib/Launcher.svelte');
  const app = read('frontend/src/App.svelte');
  const rust = read('frontend/src-tauri/src/lib.rs');

  assert.match(api, /waitForSidecarReady/);
  assert.match(api, /wait_for_sidecar_ready/);
  assert.match(launcher, /ensureSidecarReady/);
  assert.match(launcher, /await ensureSidecarReady\(\)/);
  assert.match(rust, /fn wait_for_sidecar_ready\(/);
  assert.match(rust, /generate_handler!\[[^\]]*wait_for_sidecar_ready[^\]]*\]/s);
  assert.doesNotMatch(rust, /wait_for_sidecar_ready_command/);
  assert.match(app, /invoke\('stop_sidecar_command'\)/);
  assert.match(rust, /fn stop_sidecar_command\(/);
});

test('shutdown terminates the owned sidecar process tree', () => {
  const rust = read('frontend/src-tauri/src/lib.rs');

  assert.match(rust, /let pid = child\.pid\(\)/);
  assert.match(rust, /fn terminate_process_tree\(pid: u32\)/);
  assert.match(rust, /taskkill\.exe/);
  assert.match(rust, /"\/T", "\/F"/);
});

console.log('Sidecar contract checks passed.');
