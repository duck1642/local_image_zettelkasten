import fs from 'fs';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { fileURLToPath } from 'url';
import { remote } from 'webdriverio';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..', '..');
const frontendDir = path.join(rootDir, 'frontend');
const appPath = process.env.LMZ_TAURI_APP_PATH || path.join(frontendDir, 'src-tauri', 'target', 'debug', process.platform === 'win32' ? 'app.exe' : 'app');
const configPath = process.env.LMZ_PERF_CONFIG_PATH;
const backendUrl = process.env.LMZ_PERF_BACKEND_URL || 'http://127.0.0.1:8000';
const tauriDriverPath = process.env.TAURI_DRIVER || path.join(process.env.USERPROFILE || '', '.cargo', 'bin', process.platform === 'win32' ? 'tauri-driver.exe' : 'tauri-driver');
const edgeDriverPath = process.env.MSEDGEDRIVER_PATH || 'msedgedriver';
const metrics = [];
let backendProcess;
let tauriDriverProcess;
let browser;

if (!configPath) {
  console.error('LMZ_PERF_CONFIG_PATH is required');
  process.exit(2);
}

function nowMs() {
  return performance.now();
}

async function measure(name, fn) {
  const start = nowMs();
  const result = await fn();
  metrics.push({ name, duration_ms: Math.round((nowMs() - start) * 100) / 100, ok: true });
  return result;
}

async function waitFor(fn, timeoutMs = 60000, intervalMs = 150) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw lastError || new Error('timed out waiting for condition');
}

function buildTauri() {
  const result = spawnSync('cmd', ['/c', 'npm.cmd', 'run', 'tauri', 'build', '--', '--debug', '--no-bundle'], {
    cwd: frontendDir,
    stdio: 'inherit',
    env: { ...process.env, LMZ_SKIP_SIDECAR: '1' },
    shell: false
  });
  if (result.status !== 0) throw new Error(`Tauri debug build failed with exit code ${result.status}: ${result.error || ''}`);
}

async function startBackend() {
  const env = {
    ...process.env,
    LMZ_CONFIG_PATH: configPath,
    PYTHONPATH: path.join(rootDir, 'backend') + path.delimiter + (process.env.PYTHONPATH || '')
  };
  backendProcess = spawn(process.env.PYTHON || 'python', [path.join(rootDir, 'backend', 'web_api.py')], {
    cwd: path.join(rootDir, 'backend'),
    env,
    stdio: 'ignore',
    windowsHide: true
  });
  await waitFor(async () => {
    const response = await fetch(`${backendUrl}/api/session-key`);
    return response.ok;
  }, 60000, 350);
}

async function startTauriDriver() {
  const args = [];
  if (edgeDriverPath) args.push('--native-driver', edgeDriverPath);
  tauriDriverProcess = spawn(tauriDriverPath, args, {
    stdio: 'ignore',
    env: { ...process.env, LMZ_SKIP_SIDECAR: '1' },
    windowsHide: true
  });
  await waitFor(async () => {
    const response = await fetch('http://127.0.0.1:4444/status');
    return response.ok;
  }, 30000, 150);
}

async function createSession() {
  browser = await remote({
    host: '127.0.0.1',
    port: 4444,
    capabilities: {
      'tauri:options': {
        application: appPath
      }
    },
    connectionRetryTimeout: 120000
  });
}

async function count(selector) {
  return browser.execute((sel) => document.querySelectorAll(sel).length, selector);
}

async function visibleTileCount() {
  return count('[data-testid="vault-tile"]');
}

async function scrollToRatio(ratio) {
  await browser.execute((nextRatio) => {
    const el = document.querySelector('[data-testid="virtual-scroller"]');
    if (!el) throw new Error('virtual scroller missing');
    el.scrollTop = (el.scrollHeight - el.clientHeight) * Number(nextRatio);
    el.dispatchEvent(new Event('scroll'));
  }, ratio);
  await browser.pause(180);
}

async function noOverlap(selector) {
  return browser.execute((sel) => {
    const boxes = Array.from(document.querySelectorAll(sel))
      .map((node) => {
        const rect = node.getBoundingClientRect();
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
      })
      .filter((box) => box.width > 1 && box.height > 1);
    const tolerance = 2;
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i];
        const b = boxes[j];
        const horizontal = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const vertical = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (horizontal > tolerance && vertical > tolerance) return false;
      }
    }
    return true;
  }, selector);
}

async function runCommand(command) {
  const input = await browser.$('[data-testid="vault-search-input"]');
  await input.setValue(command);
  await browser.keys('Enter');
}

async function writeResults(ok, error = null) {
  const runId = path.basename(path.dirname(configPath));
  const dir = path.join(rootDir, 'tests', 'perf-results', runId);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'tauri-webview.json'), JSON.stringify({
    kind: 'tauri-webview',
    run_id: runId,
    config_path: configPath,
    backend_url: backendUrl,
    app_path: appPath,
    ok,
    error: error ? String(error.stack || error) : null,
    metrics
  }, null, 2));
}

async function runPerf() {
  await measure('tauri-debug-build', async () => buildTauri());
  await measure('backend-ready', async () => startBackend());
  await measure('tauri-driver-ready', async () => startTauriDriver());
  await measure('tauri-session-ready', async () => createSession());

  await measure('first-tile-visible', async () => {
    await waitFor(async () => (await visibleTileCount()) > 0, 90000);
  });
  const initialTiles = await visibleTileCount();
  if (initialTiles <= 0 || initialTiles >= 300) throw new Error(`unexpected visible tile count: ${initialTiles}`);

  for (const [layout, itemSelector] of [
    ['masonry', '[data-testid="masonry-renderer-item"]'],
    ['grid', '[data-testid="grid-renderer-item"]']
  ]) {
    if (layout === 'grid') {
      await measure('layout-switch-grid', async () => {
        await runCommand('/grid');
        await waitFor(async () => (await count(itemSelector)) > 0);
      });
    }
    for (const [label, ratio] of [['top', 0], ['middle', 0.5], ['bottom', 1]]) {
      await measure(`${layout}-scroll-${label}-settle`, async () => {
        await scrollToRatio(ratio);
        await waitFor(async () => (await count(itemSelector)) > 0);
        if (!(await noOverlap(itemSelector))) throw new Error(`${layout} overlap at ${label}`);
        const tiles = await visibleTileCount();
        if (tiles <= 0 || tiles >= 300) throw new Error(`${layout} unbounded visible tiles: ${tiles}`);
      });
    }
  }

  await measure('media-filter-video-render', async () => {
    await runCommand('/media-video');
    await waitFor(async () => (await count('[data-testid="vault-tile"] video')) > 0);
    const videoOk = await browser.execute(() => {
      const video = document.querySelector('[data-testid="vault-tile"] video');
      return Boolean(video && video.getAttribute('src') && video.getAttribute('poster'));
    });
    if (!videoOk) throw new Error('video tile missing src/poster');
  });

  await measure('logs-navigation', async () => {
    await (await browser.$('button=App Logs')).click();
    await waitFor(async () => browser.execute(() => document.body.innerText.includes('App Logs')));
  });

  await measure('settings-navigation', async () => {
    await (await browser.$('button=Settings')).click();
    await waitFor(async () => browser.execute(() => document.body.innerText.includes('System Settings')));
  });
}

async function cleanup() {
  try {
    if (browser) await browser.deleteSession();
  } catch {}
  if (tauriDriverProcess && tauriDriverProcess.exitCode === null) tauriDriverProcess.kill();
  if (backendProcess && backendProcess.exitCode === null) {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/F', '/T', '/PID', String(backendProcess.pid)], { stdio: 'ignore', windowsHide: true });
    } else {
      backendProcess.kill();
    }
  }
}

try {
  await runPerf();
  await writeResults(true);
  await cleanup();
  console.log(JSON.stringify({ ok: true, metrics }, null, 2));
} catch (error) {
  await writeResults(false, error);
  await cleanup();
  console.error(error);
  process.exit(1);
}
