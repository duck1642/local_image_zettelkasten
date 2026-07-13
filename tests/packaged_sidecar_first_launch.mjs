import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const sidecar = path.resolve(process.argv[2] || 'frontend/src-tauri/bin/lmz-api-x86_64-pc-windows-msvc.exe');
const dataRoot = path.resolve(process.argv[3] || path.join('C:/tmp', `lmz-packaged-first-launch-${Date.now()}`));
const mode = process.argv.includes('--app') ? 'desktop-app' : 'sidecar';
const apiBase = 'http://127.0.0.1:8000';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function apiJson(endpoint, init = {}) {
  const response = await fetch(`${apiBase}${endpoint}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${endpoint} failed ${response.status}: ${JSON.stringify(payload)}`);
  return payload;
}

async function waitForApi(expectedNonce, timeoutMs = 120_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(`${apiBase}/api/runtime/health`);
      const payload = await response.json().catch(() => ({}));
      if (
        response.ok
        && payload.service === 'lmz-api'
        && payload.ready === true
        && payload.protocol_version === 1
        && payload.nonce === expectedNonce
      ) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('Timed out waiting for the packaged sidecar');
}

function runningSidecarPids() {
  if (process.platform !== 'win32') return [];
  const processName = path.basename(sidecar, path.extname(sidecar));
  const result = spawnSync(
    'powershell.exe',
    [
      '-NoProfile',
      '-Command',
      `(Get-Process -Name '${processName}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) -join ','`
    ],
    { windowsHide: true, encoding: 'utf8' }
  );
  return String(result.stdout || '')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value) && value > 0);
}

async function stop(child, baselinePids = new Set()) {
  const candidates = new Set(runningSidecarPids().filter((pid) => !baselinePids.has(pid)));
  if (child?.pid) candidates.add(child.pid);
  if (process.platform === 'win32') {
    for (const pid of candidates) {
      spawnSync('taskkill.exe', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      spawnSync('powershell.exe', ['-NoProfile', '-Command', `Stop-Process -Id ${pid} -Force -ErrorAction SilentlyContinue`], { windowsHide: true, stdio: 'ignore' });
      try { process.kill(pid, 'SIGKILL'); } catch {}
    }
  } else if (child && child.exitCode === null) {
    child.kill('SIGTERM');
  }
  if (child && child.exitCode === null) {
    await Promise.race([
      new Promise((resolve) => child.once('exit', resolve)),
      new Promise((resolve) => setTimeout(resolve, 10_000))
    ]);
  }
  if (child?.exitCode === null) {
    try { child.kill('SIGKILL'); } catch {}
  }
  child.stdout?.destroy();
  child.stderr?.destroy();
  const started = Date.now();
  while (Date.now() - started < 60_000) {
    try {
      await fetch(`${apiBase}/api/app/settings`);
    } catch {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Packaged ${mode} backend remained reachable after process-tree termination`);
}

async function runCycle(label) {
  const output = [];
  const baselinePids = new Set(runningSidecarPids());
  const launchNonce = `packaged-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const child = spawn(sidecar, [], {
    cwd: path.dirname(sidecar),
    env: {
      ...process.env,
      LMZ_DATA_ROOT: dataRoot,
      LMZ_DISABLE_RELOAD: '1',
      LMZ_STARTUP_NONCE: launchNonce
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  child.stdout.on('data', (chunk) => output.push(String(chunk)));
  child.stderr.on('data', (chunk) => output.push(String(chunk)));
  try {
    await waitForApi(launchNonce);
    const settingsResponse = await fetch(`${apiBase}/api/app/settings`, {
      headers: { Origin: 'http://tauri.localhost' }
    });
    assert(settingsResponse.ok, `${label}: app settings request failed ${settingsResponse.status}`);
    const exposedHeaders = new Set(
      (settingsResponse.headers.get('access-control-expose-headers') || '')
        .split(',')
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean)
    );
    assert(exposedHeaders.has('etag'), `${label}: packaged API does not expose ETag to the Tauri origin`);
    const settings = await settingsResponse.json();
    assert(settings.schema_version === 1, `${label}: invalid settings schema`);
    const workspaces = await apiJson('/api/workspaces');
    assert(workspaces.active === 'default', `${label}: default workspace is not active`);
    assert(workspaces.items?.length === 1 && workspaces.items[0].exists, `${label}: default workspace is unavailable`);
    const sessionKey = (await apiJson('/api/session-key')).key;
    const loaded = await apiJson('/api/workspaces/default/load', {
      method: 'POST',
      headers: { 'X-LMZ-API-KEY': sessionKey }
    });
    assert(loaded.status === 'success', `${label}: default workspace did not load`);
    const runtime = await apiJson('/api/runtime/session');
    assert(runtime.loaded === true, `${label}: runtime did not become active`);
    assert(path.resolve(runtime.workspace.root) === path.join(dataRoot, 'default'), `${label}: runtime escaped the data home`);
    return { label, workspace: runtime.workspace.root, vault: runtime.vault.root };
  } catch (error) {
    throw new Error(`${error.message}\nPackaged ${mode} output:\n${output.join('')}`);
  } finally {
    await stop(child, baselinePids);
  }
}

if (!fs.existsSync(sidecar)) throw new Error(`Packaged ${mode} binary not found: ${sidecar}`);
if (fs.existsSync(dataRoot)) throw new Error(`Refusing to reuse or delete an existing test data root: ${dataRoot}`);

try {
  const existing = await fetch(`${apiBase}/api/app/settings`);
  if (existing.ok) throw new Error('Port 8000 is already serving LMZ; stop it before packaged validation');
} catch (error) {
  if (String(error.message || '').includes('already serving')) throw error;
}

const bundleDir = path.dirname(sidecar);
const forbiddenBundleData = ['config', 'data', 'logs', 'secrets'].map((name) => path.join(bundleDir, name));
const existedBefore = new Map(forbiddenBundleData.map((entry) => [entry, fs.existsSync(entry)]));
const first = await runCycle('first launch');
const second = await runCycle('restart');

const required = [
  'app/settings.yaml', 'app/workspaces.yaml', 'app/secrets', 'app/logs', 'app/models', 'app/cache',
  'default/config.yaml', 'default/data', 'default/backups', 'default/exports'
];
for (const relative of required) {
  assert(fs.existsSync(path.join(dataRoot, relative)), `missing data-home entry: ${relative}`);
}
if (mode === 'desktop-app') {
  const appLogs = fs.readdirSync(path.join(dataRoot, 'app', 'logs'));
  assert(appLogs.some((name) => name.startsWith('tauri')), 'desktop restart did not route Tauri logs into app/logs');
}
for (const entry of forbiddenBundleData) {
  assert(fs.existsSync(entry) === existedBefore.get(entry), `packaged launch wrote mutable data beside the sidecar: ${entry}`);
}

const report = {
  version: 1,
  mode,
  sidecar,
  data_root: dataRoot,
  first,
  second,
  source_deleted: false,
  install_directory_unchanged: true,
  completed_at: new Date().toISOString()
};
fs.writeFileSync(path.join(dataRoot, 'app', 'packaged-first-launch-report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
