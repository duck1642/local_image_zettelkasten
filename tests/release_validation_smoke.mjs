import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const backendRoot = path.join(root, 'backend');
const apiBase = 'http://127.0.0.1:8000';

function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith('--')) continue;
    const key = arg.slice(2);
    values[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return values;
}

const args = parseArgs(process.argv.slice(2));
const sourceDefault = path.resolve(String(args['source-default'] || ''));
const externalConfig = path.resolve(String(args['external-config'] || 'F:/ARCHIVE/main/lmz/config.yaml'));
const modelsSource = path.resolve(String(args['models-source'] || path.join(root, 'data/models/wd-vit-tagger-v3')));
const reportPath = path.resolve(String(args.report || path.join(root, 'release-validation-smoke-report.json')));
const tempParent = path.resolve(String(args['temp-root'] || path.join(root, 'tests')));

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function runBootstrap(dataRoot) {
  const result = spawnSync('python', ['-c', [
    'import sys',
    'from app_paths import app_paths_for_root',
    'from config_repository import bootstrap_data_home',
    'bootstrap_data_home(app_paths_for_root(sys.argv[1]))',
  ].join(';'), dataRoot], {
    cwd: backendRoot,
    env: { ...process.env, PYTHONPATH: backendRoot },
    encoding: 'utf8',
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(`data-home bootstrap failed: ${result.stderr || result.stdout}`);
  }
}

function writeWorkspaceRegistry(dataRoot) {
  const registry = [
    'schema_version: 1',
    'active_workspace: default',
    'workspaces:',
    '  default:',
    '    name: Default',
    '    config_path: default/config.yaml',
    '  obsidian-main:',
    '    name: Obsidian Main',
    `    config_path: ${externalConfig.replaceAll('\\', '/')}`,
    '',
  ].join('\n');
  fs.writeFileSync(path.join(dataRoot, 'app', 'workspaces.yaml'), registry, 'utf8');
}

function sqliteIntegrity(database) {
  const result = spawnSync('python', ['-c', [
    'import sqlite3, sys',
    'conn = sqlite3.connect(sys.argv[1])',
    'value = conn.execute("PRAGMA integrity_check").fetchone()[0]',
    'conn.close()',
    'print(value)',
    'raise SystemExit(0 if value == "ok" else 1)',
  ].join(';'), database], { encoding: 'utf8', windowsHide: true });
  return { ok: result.status === 0 && result.stdout.trim() === 'ok', result: result.stdout.trim() || result.stderr.trim() };
}

function sqliteItemCount(database) {
  const result = spawnSync('python', ['-c', [
    'import sqlite3, sys',
    'conn = sqlite3.connect(sys.argv[1])',
    'print(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])',
    'conn.close()',
  ].join(';'), database], { encoding: 'utf8', windowsHide: true });
  if (result.status !== 0) throw new Error(`SQLite count failed: ${result.stderr || result.stdout}`);
  return Number(result.stdout.trim());
}

function listFiles(directory) {
  if (!fs.existsSync(directory)) return [];
  const output = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) output.push(...listFiles(full));
    else if (entry.isFile()) output.push(full);
  }
  return output;
}

async function waitFor(url, predicate = (response) => response.ok, timeoutMs = 120_000) {
  const started = Date.now();
  let lastError = '';
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (await predicate(response)) return response;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = String(error.message || error);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

let sessionKey = '';
async function refreshSessionKey() {
  const response = await fetch(`${apiBase}/api/session-key`);
  assert(response.ok, `session key failed: ${response.status}`);
  sessionKey = (await response.json()).key || '';
  assert(sessionKey, 'backend returned an empty session key');
  return sessionKey;
}

async function apiJson(endpoint, init = {}) {
  const method = String(init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers || {});
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    if (!sessionKey) await refreshSessionKey();
    headers.set('X-LMZ-API-KEY', sessionKey);
  }
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${apiBase}${endpoint}`, { ...init, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${method} ${endpoint} failed ${response.status}: ${JSON.stringify(payload)}`);
  return payload;
}

async function itemCount() {
  const payload = await apiJson('/api/items?limit=100');
  return payload.items?.length || 0;
}

async function waitForLocalIngest() {
  const started = Date.now();
  let latest = null;
  while (Date.now() - started < 180_000) {
    latest = await apiJson('/api/local-ingest/status');
    if (!latest.running) {
      const phase = String(latest.phase || '').toLowerCase();
      if (phase === 'error' || Number(latest.summary?.failed || 0) > 0) {
        throw new Error(`local ingest failed: ${JSON.stringify(latest)}`);
      }
      return latest;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`local ingest timed out: ${JSON.stringify(latest)}`);
}

async function waitForMetadata() {
  const started = Date.now();
  let latest = null;
  while (Date.now() - started < 180_000) {
    latest = await apiJson('/api/metadata-index/status');
    const job = latest.maintenance_rebuild || {};
    if (job.running === false && (!job.status || ['completed', 'idle'].includes(String(job.status)))) return latest;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`metadata rebuild timed out: ${JSON.stringify(latest)}`);
}

function startBackend(dataRoot, outputPath) {
  const output = fs.openSync(outputPath, 'a');
  const nonce = `goal-e-smoke-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  try {
    const child = spawn('python', ['web_api.py'], {
      cwd: backendRoot,
      env: {
        ...process.env,
        PYTHONPATH: backendRoot,
        LMZ_DATA_ROOT: dataRoot,
        LMZ_CONFIG_PATH: path.join(dataRoot, 'default', 'config.yaml'),
        LMZ_DISABLE_RELOAD: '1',
        LMZ_STARTUP_NONCE: nonce,
      },
      stdio: ['ignore', output, output],
      windowsHide: true,
    });
    child.lmzNonce = nonce;
    return child;
  } finally {
    fs.closeSync(output);
  }
}

async function waitForBackend(child) {
  await waitFor(`${apiBase}/api/runtime/health`, async (response) => {
    const payload = await response.json().catch(() => ({}));
    return response.ok
      && payload.service === 'lmz-api'
      && payload.ready === true
      && payload.protocol_version === 1
      && payload.nonce === child.lmzNonce;
  });
}

async function waitForProcessExit(child, timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (child.exitCode !== null || child.signalCode !== null) return true;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return child.exitCode !== null || child.signalCode !== null;
}

async function stopBackend(child) {
  if (!child) return;
  if (child.exitCode === null && child.signalCode === null) {
    if (process.platform === 'win32' && child.pid) {
      const result = spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      if (result.status !== 0 && child.exitCode === null) child.kill('SIGTERM');
    } else {
      child.kill('SIGTERM');
    }
  }
  let exited = await waitForProcessExit(child, 15_000);
  if (!exited) {
    child.kill('SIGKILL');
    exited = await waitForProcessExit(child, 5_000);
  }
  assert(exited, `backend process ${child.pid} did not exit`);
  const started = Date.now();
  while (Date.now() - started < 15_000) {
    try {
      await fetch(`${apiBase}/api/runtime/health`);
    } catch {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`backend port remained reachable after stopping process ${child.pid}`);
}

function pngFixture(suffix = '') {
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
  return Buffer.concat([png, Buffer.from(suffix, 'utf8')]);
}

async function main() {
  assert(sourceDefault && fs.existsSync(sourceDefault), `missing --source-default: ${sourceDefault}`);
  assert(fs.existsSync(externalConfig), `missing --external-config: ${externalConfig}`);
  assert(fs.existsSync(path.join(modelsSource, 'model.onnx')), `missing WD model: ${modelsSource}`);
  assert(fs.existsSync(path.join(modelsSource, 'selected_tags.csv')), `missing WD labels: ${modelsSource}`);

  fs.mkdirSync(tempParent, { recursive: true });
  const dataRoot = path.join(tempParent, `.goal-d-smoke-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  assert(!fs.existsSync(dataRoot), `refusing to reuse existing smoke root: ${dataRoot}`);
  const outputPath = path.join(dataRoot, 'backend.log');
  const stageDefault = path.join(dataRoot, 'default');
  const sourceConfig = path.join(sourceDefault, 'config.yaml');
  assert(fs.existsSync(sourceConfig), `staged source has no config.yaml: ${sourceConfig}`);

  runBootstrap(dataRoot);
  fs.cpSync(sourceDefault, stageDefault, { recursive: true, force: true });
  fs.cpSync(modelsSource, path.join(dataRoot, 'app', 'models', 'wd-vit-tagger-v3'), { recursive: true, force: true });
  writeWorkspaceRegistry(dataRoot);

  const externalConfigBefore = fs.readFileSync(externalConfig);
  const report = {
    version: 1,
    data_root: dataRoot,
    source_default: sourceDefault,
    external_config: externalConfig,
    steps: [],
  };
  const record = (step, details = {}) => report.steps.push({ step, ...details });
  let backend = null;

  try {
    backend = startBackend(dataRoot, outputPath);
    await waitForBackend(backend);
    await refreshSessionKey();

    const settingsResponse = await fetch(`${apiBase}/api/app/settings`);
    assert(settingsResponse.ok, 'settings preflight failed');
    const settings = await settingsResponse.json();
    const etag = settingsResponse.headers.get('etag');
    settings.tagging.enabled = true;
    settings.tagging.device = 'cpu';
    settings.tagging.model_repo = 'SmilingWolf/wd-vit-tagger-v3';
    await apiJson('/api/app/settings', { method: 'PUT', headers: { 'If-Match': etag }, body: JSON.stringify(settings) });

    const workspaces = await apiJson('/api/workspaces');
    const initialWorkspace = workspaces.active;
    assert(initialWorkspace === 'default', `staged smoke must start on default, got ${initialWorkspace}`);
    const defaultEntry = workspaces.items.find((item) => item.id === 'default');
    const externalEntry = workspaces.items.find((item) => item.id === 'obsidian-main');
    assert(defaultEntry?.exists, 'staged default workspace is unavailable');
    assert(externalEntry?.exists, 'registered external workspace is unavailable');
    assert(path.resolve(externalEntry.config_path) === externalConfig, `external config mismatch: ${externalEntry.config_path}`);
    const runtime = await apiJson('/api/runtime/session');
    assert(runtime.loaded === true, 'default runtime did not load');
    assert(path.resolve(runtime.workspace.root) === stageDefault, `runtime escaped staged default: ${runtime.workspace.root}`);
    const databasePath = path.join(stageDefault, 'data', 'vaults', 'default', 'db', 'lmz_main.db');
    const healthBeforeRepair = await apiJson('/api/vaults/default/health');
    const repairResult = await apiJson('/api/vaults/default/repair', {
      method: 'POST',
      body: JSON.stringify({ actions: ['thumbnails', 'derived_cache'], confirm_destructive: true }),
    });
    const healthAfterRepair = await apiJson('/api/vaults/default/health');
    assert(healthAfterRepair.issue_count === 0, `migrated default remains unhealthy after thumbnail repair: ${JSON.stringify(healthAfterRepair)}`);
    record('launch and default workspace', {
      initial_workspace: initialWorkspace,
      item_count: sqliteItemCount(databasePath),
      health_before_repair: healthBeforeRepair,
      repair: repairResult,
      health_after_repair: healthAfterRepair,
    });

    const fixturePath = path.join(dataRoot, 'input', 'goal-d-ingest.png');
    fs.mkdirSync(path.dirname(fixturePath), { recursive: true });
    fs.writeFileSync(fixturePath, pngFixture('-ingest'));
    const beforeIngest = sqliteItemCount(databasePath);
    const ingestStart = await apiJson('/api/local-ingest/start', {
      method: 'POST',
      body: JSON.stringify({
        paths: [fixturePath],
        skip_similarity: true,
        defaults: { artist: 'Goal D Smoke', platform: 'Local', source_url: 'goal-d://ingest' },
      }),
    });
    const ingestStatus = await waitForLocalIngest();
    const afterIngest = sqliteItemCount(databasePath);
    assert(afterIngest > beforeIngest, `ingest did not add an item: ${JSON.stringify(ingestStatus)}`);
    const itemsAfterIngest = (await apiJson('/api/items?limit=100')).items || [];
    const ingested = itemsAfterIngest.find((item) => item.artist === 'Goal D Smoke');
    assert(ingested?.hash, 'ingested item was not returned by the library API');
    record('controlled ingest', { run_id: ingestStart.run_id, summary: ingestStatus.summary, hash: ingested.hash });

    const reviewFilename = 'goal-d-review.png';
    const reviewPath = path.join(runtime.vault.root, 'review', reviewFilename);
    fs.writeFileSync(reviewPath, pngFixture('-review'));
    fs.writeFileSync(`${reviewPath}.json`, JSON.stringify({ state: 'pending', metadata: { artist: 'Goal D Review' } }, null, 2));
    const reviewItems = await apiJson('/api/review');
    assert(reviewItems.some((item) => item.filename === reviewFilename), 'controlled review fixture was not visible');
    const reviewResult = await apiJson(`/api/review/${encodeURIComponent(reviewFilename)}/action?action=variant`, { method: 'POST' });
    assert(reviewResult.status === 'success', `review action failed: ${JSON.stringify(reviewResult)}`);
    record('deterministic review action', { action: 'variant', result: reviewResult });

    const latestItems = (await apiJson('/api/items?limit=100')).items || [];
    const reviewed = latestItems.find((item) => item.artist === 'Goal D Review');
    assert(reviewed?.hash, 'reviewed item was not added to the library');
    const patched = await apiJson(`/api/items/${reviewed.hash}`, {
      method: 'PATCH',
      body: JSON.stringify({ artist: 'Goal D Metadata', topics: ['goal-d-smoke'] }),
    });
    assert(patched.artist === 'Goal D Metadata', 'metadata patch did not update artist');
    const metadataJob = await apiJson('/api/metadata-index/rebuild', { method: 'POST' });
    const metadataStatus = await waitForMetadata();
    assert(metadataStatus.ready === true, 'metadata index is not ready after rebuild');
    assert(Number(metadataStatus.errors || 0) === 0, `metadata index has errors: ${JSON.stringify(metadataStatus)}`);
    assert(Number(metadataStatus.dirty || 0) === 0, `metadata index remains dirty: ${JSON.stringify(metadataStatus)}`);
    record('metadata update and index', { hash: reviewed.hash, rebuild: metadataJob, status: metadataStatus });

    const thumbnailResponse = await fetch(`${apiBase}/api/thumbnails/${ingested.hash}`);
    assert(thumbnailResponse.ok, `thumbnail request failed: ${thumbnailResponse.status}`);
    const ingestPath = await apiJson(`/api/items/${ingested.hash}/path`);
    const storageId = path.basename(ingestPath.absolute_path).split('.')[0];
    const wdCache = path.join(runtime.vault.root, 'wd-tags', ingested.hash.slice(0, 2), `${storageId}.json`);
    assert(fs.existsSync(wdCache), `WD cache missing: ${wdCache}`);
    record('thumbnail and WD tagging', { thumbnail_status: thumbnailResponse.status, wd_cache: wdCache });

    const health = await apiJson('/api/vaults/default/health');
    assert(health.issue_count === 0, `default vault remains unhealthy: ${JSON.stringify(health)}`);
    assert(Number(health.hash_mismatches?.length || 0) === 0, `default vault hash mismatches: ${JSON.stringify(health.hash_mismatches)}`);
    const integrityBefore = sqliteIntegrity(path.join(stageDefault, 'data', 'vaults', 'default', 'db', 'lmz_main.db'));
    assert(integrityBefore.ok, `SQLite integrity before restart failed: ${integrityBefore.result}`);
    record('health and SQLite integrity', { issue_count: health.issue_count, integrity: integrityBefore.result });

    const externalBefore = fs.readFileSync(externalConfig);
    const externalSwitch = await apiJson('/api/workspaces/active', { method: 'POST', body: JSON.stringify({ id: 'obsidian-main' }) });
    assert(externalSwitch.status === 'success', `external workspace switch failed: ${JSON.stringify(externalSwitch)}`);
    const switched = await apiJson('/api/runtime/session');
    assert(path.resolve(switched.workspace.root) === path.dirname(externalConfig), `external runtime root mismatch: ${switched.workspace.root}`);
    const externalList = await apiJson('/api/workspaces');
    assert(externalList.active === 'obsidian-main', 'external workspace was not active after switch');
    await apiJson('/api/workspaces/active', { method: 'POST', body: JSON.stringify({ id: initialWorkspace }) });
    const restored = await apiJson('/api/workspaces');
    assert(restored.active === initialWorkspace, `active workspace was not restored: ${restored.active}`);
    assert(Buffer.compare(externalBefore, fs.readFileSync(externalConfig)) === 0, 'external workspace config changed during open/switch');
    assert(fs.existsSync(path.dirname(externalConfig)), 'external workspace root disappeared');
    record('external workspace open and restore', { initial_workspace: initialWorkspace, restored_workspace: restored.active, config_unchanged: true });

    await stopBackend(backend);
    backend = null;
    sessionKey = '';
    backend = startBackend(dataRoot, outputPath);
    await waitForBackend(backend);
    const restartWorkspaces = await apiJson('/api/workspaces');
    assert(restartWorkspaces.active === initialWorkspace, `restart changed active workspace: ${restartWorkspaces.active}`);
    const restartRuntime = await apiJson('/api/runtime/session');
    assert(path.resolve(restartRuntime.workspace.root) === stageDefault, 'restart did not reopen staged default workspace');
    const afterRestart = sqliteItemCount(databasePath);
    assert(afterRestart >= afterIngest, `restart lost items: before=${afterIngest} after=${afterRestart}`);
    const integrityAfter = sqliteIntegrity(path.join(stageDefault, 'data', 'vaults', 'default', 'db', 'lmz_main.db'));
    assert(integrityAfter.ok, `SQLite integrity after restart failed: ${integrityAfter.result}`);
    record('restart and persistence', { item_count: afterRestart, integrity: integrityAfter.result });

    const appLogs = listFiles(path.join(dataRoot, 'app', 'logs'));
    const vaultLogs = listFiles(path.join(stageDefault, 'data', 'vaults', 'default', 'logs'));
    assert(appLogs.length > 0, 'app logs were not produced');
    assert(vaultLogs.length > 0, 'vault logs were not produced');
    report.artifacts = {
      backend_log: outputPath,
      app_logs: appLogs,
      vault_logs: vaultLogs,
      database: databasePath,
    };
    report.completed_at = new Date().toISOString();
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), 'utf8');
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await stopBackend(backend);
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
