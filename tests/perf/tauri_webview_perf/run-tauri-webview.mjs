import fs from 'fs';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { fileURLToPath } from 'url';
import { remote } from 'webdriverio';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..', '..');
const frontendDir = path.join(rootDir, 'frontend');
const configPath = process.env.LMZ_PERF_CONFIG_PATH;
const backendUrl = process.env.LMZ_PERF_BACKEND_URL || 'http://127.0.0.1:8000';
const appPath = process.env.LMZ_TAURI_APP_PATH || path.join(frontendDir, 'src-tauri', 'target', 'debug', process.platform === 'win32' ? 'app.exe' : 'app');
const tauriDriverPath = process.env.TAURI_DRIVER || path.join(process.env.USERPROFILE || '', '.cargo', 'bin', process.platform === 'win32' ? 'tauri-driver.exe' : 'tauri-driver');
const edgeDriverPath = resolveExecutable(process.env.MSEDGEDRIVER_PATH || 'msedgedriver');

if (!configPath) {
  console.error('LMZ_PERF_CONFIG_PATH is required');
  process.exit(2);
}

const runId = path.basename(path.dirname(configPath));
const resultDir = path.join(rootDir, 'tests', 'perf-results', runId);
const manifestPath = path.join(path.dirname(configPath), 'manifest.json');
fs.mkdirSync(resultDir, { recursive: true });

const metrics = [];
const memorySamples = [];
const domSamples = [];
let backendProcess;
let tauriDriverProcess;
let browser;

const diagnostics = {
  config_path: configPath,
  manifest_path: manifestPath,
  backend_url: backendUrl,
  app_path: appPath,
  tauri_driver: tauriDriverPath,
  msedgedriver: edgeDriverPath,
  webdriver_port: 4444,
  sandbox_env_keys: Object.keys(process.env).filter((key) => /sandbox|codex/i.test(key)).sort()
};

async function measure(name, fn) {
  const start = nowMs();
  const result = await fn();
  metrics.push({ name, duration_ms: Math.round((nowMs() - start) * 100) / 100, ok: true });
  return result;
}

function nowMs() {
  return performance.now();
}

function resolveExecutable(command) {
  if (!command) return command;
  if (path.isAbsolute(command) || command.includes(path.sep) || (process.platform === 'win32' && command.includes('/'))) {
    return command;
  }
  const lookup = process.platform === 'win32'
    ? spawnSync('where.exe', [command], { encoding: 'utf8', shell: false })
    : spawnSync('which', [command], { encoding: 'utf8', shell: false });
  if (lookup.status !== 0) return command;
  const resolved = String(lookup.stdout || '').split(/\r?\n/).map((line) => line.trim()).find(Boolean);
  return resolved || command;
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

function loadManifest() {
  if (!fs.existsSync(manifestPath)) return {};
  return JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
}

function attachLog(processHandle, logPath) {
  const stream = fs.createWriteStream(logPath, { flags: 'a' });
  processHandle.stdout?.pipe(stream, { end: false });
  processHandle.stderr?.pipe(stream, { end: false });
  processHandle.on('exit', (code, signal) => {
    stream.write(`\n[process exited code=${code} signal=${signal}]\n`);
    stream.end();
  });
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
    LMZ_DISABLE_RELOAD: '1',
    PYTHONPATH: path.join(rootDir, 'backend') + path.delimiter + (process.env.PYTHONPATH || '')
  };
  backendProcess = spawn(process.env.PYTHON || 'python', [path.join(rootDir, 'backend', 'web_api.py')], {
    cwd: path.join(rootDir, 'backend'),
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true
  });
  attachLog(backendProcess, path.join(resultDir, 'backend.log'));
  await waitFor(async () => {
    if (backendProcess.exitCode !== null) {
      throw new Error(`backend exited before ready with code ${backendProcess.exitCode}`);
    }
    const response = await fetch(`${backendUrl}/api/session-key`);
    return response.ok;
  }, 60000, 350);
}

async function startTauriDriver() {
  const args = [];
  if (edgeDriverPath) args.push('--native-driver', edgeDriverPath);
  tauriDriverProcess = spawn(tauriDriverPath, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, LMZ_SKIP_SIDECAR: '1' },
    windowsHide: true
  });
  attachLog(tauriDriverProcess, path.join(resultDir, 'tauri-driver.log'));
  await waitFor(async () => {
    if (tauriDriverProcess.exitCode !== null) {
      throw new Error(`tauri-driver exited before ready with code ${tauriDriverProcess.exitCode}`);
    }
    const response = await fetch('http://127.0.0.1:4444/status');
    return response.ok;
  }, 30000, 150);
}

async function createSession() {
  browser = await remote({
    host: '127.0.0.1',
    port: 4444,
    logLevel: 'error',
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

async function domStats(label) {
  const stats = await browser.execute((sampleLabel) => ({
    label: sampleLabel,
    tiles: document.querySelectorAll('[data-testid="vault-tile"]').length,
    images: document.querySelectorAll('[data-testid="vault-tile"] img').length,
    videos: document.querySelectorAll('[data-testid="vault-tile"] video').length,
    dom_nodes: document.getElementsByTagName('*').length
  }), label);
  domSamples.push(stats);
  return stats;
}

async function memorySnapshot(label) {
  let backendMb = null;
  let backendOk = false;
  let backendError = null;
  try {
    const response = await fetch(`${backendUrl}/api/system/memory`);
    backendOk = response.ok;
    if (response.ok) {
      const payload = await response.json();
      backendMb = Number.isFinite(Number(payload.backend_mb)) ? Number(payload.backend_mb) : null;
    }
  } catch (error) {
    backendError = String(error);
  }
  let frontendMb = null;
  if (browser) {
    frontendMb = await browser.execute(() => {
      const memory = performance.memory;
      if (!memory?.usedJSHeapSize) return null;
      return Math.round((memory.usedJSHeapSize / 1024 / 1024) * 10) / 10;
    });
  }
  const sample = {
    label,
    backend_ok: backendOk,
    backend_mb: backendMb,
    frontend_mb: frontendMb,
    total_mb: Number.isFinite(backendMb) && Number.isFinite(frontendMb) ? Math.round((backendMb + frontendMb) * 10) / 10 : null,
    error: backendError
  };
  memorySamples.push(sample);
  return sample;
}

async function scrollToRatio(ratio, settleMs = 180) {
  await browser.execute((nextRatio) => {
    const el = document.querySelector('[data-testid="virtual-scroller"]');
    if (!el) throw new Error('virtual scroller missing');
    el.scrollTop = (el.scrollHeight - el.clientHeight) * Number(nextRatio);
    el.dispatchEvent(new Event('scroll'));
  }, ratio);
  await browser.pause(settleMs);
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

async function assertRenderer(layout, itemSelector) {
  await waitFor(async () => (await count(itemSelector)) > 0);
  if (!(await noOverlap(itemSelector))) throw new Error(`${layout} overlap`);
  const stats = await domStats(`${layout}-assert`);
  if (stats.tiles <= 0 || stats.tiles >= 300) throw new Error(`${layout} unbounded visible tiles: ${stats.tiles}`);
  return stats;
}

async function scrollSweep(layout, itemSelector) {
  let maxTiles = 0;
  let maxImages = 0;
  let maxVideos = 0;
  let maxDomNodes = 0;
  for (let index = 0; index <= 12; index += 1) {
    await scrollToRatio(index / 12, 80);
    await waitFor(async () => (await count(itemSelector)) > 0);
    if (!(await noOverlap(itemSelector))) throw new Error(`${layout} overlap during sweep at step ${index}`);
    const stats = await domStats(`${layout}-sweep-${index}`);
    maxTiles = Math.max(maxTiles, stats.tiles);
    maxImages = Math.max(maxImages, stats.images);
    maxVideos = Math.max(maxVideos, stats.videos);
    maxDomNodes = Math.max(maxDomNodes, stats.dom_nodes);
  }
  if (maxTiles <= 0 || maxTiles >= 300) throw new Error(`${layout} unbounded sweep tiles: ${maxTiles}`);
  return { layout, max_tiles: maxTiles, max_images: maxImages, max_videos: maxVideos, max_dom_nodes: maxDomNodes };
}

async function searchLatency(command, label) {
  await measure(`search-${label}`, async () => {
    await runCommand(command);
    await waitFor(async () => (await visibleTileCount()) > 0, 30000);
  });
  await domStats(`search-${label}`);
}

async function writeResults(ok, error = null) {
  fs.writeFileSync(path.join(resultDir, 'tauri-webview.json'), JSON.stringify({
    kind: 'tauri-webview',
    run_id: runId,
    config_path: configPath,
    backend_url: backendUrl,
    app_path: appPath,
    ok,
    error: error ? String(error.stack || error) : null,
    diagnostics,
    metrics,
    memory: memorySamples,
    dom: domSamples
  }, null, 2));
}

async function runPerf() {
  console.log(JSON.stringify({ kind: 'tauri-webview-diagnostics', diagnostics }, null, 2));
  const manifest = loadManifest();
  const firstItem = Array.isArray(manifest.items) && manifest.items.length ? manifest.items[0] : {};

  await measure('tauri-debug-build', async () => buildTauri());
  await measure('backend-ready', async () => startBackend());
  await memorySnapshot('after_backend_ready');
  await measure('tauri-driver-ready', async () => startTauriDriver());
  await measure('tauri-session-ready', async () => createSession());
  await memorySnapshot('after_session_ready');

  await measure('first-tile-visible', async () => {
    await waitFor(async () => (await visibleTileCount()) > 0, 90000);
  });
  await domStats('first-tile-visible');
  await memorySnapshot('after_first_tile');

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
        await assertRenderer(layout, itemSelector);
      });
    }
    await measure(`${layout}-continuous-scroll-sweep`, async () => {
      const sweep = await scrollSweep(layout, itemSelector);
      metrics.push({ name: `${layout}-sweep-max-counts`, ok: true, ...sweep });
    });
    await memorySnapshot(`after_${layout}_scroll_sweep`);
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
  await measure('video-unmount-bounded-scroll', async () => {
    let maxVideos = 0;
    for (const ratio of [0, 0.25, 0.5, 0.75, 1, 0]) {
      await scrollToRatio(ratio, 120);
      const stats = await domStats(`video-scroll-${ratio}`);
      maxVideos = Math.max(maxVideos, stats.videos);
    }
    if (maxVideos <= 0 || maxVideos >= 300) throw new Error(`unbounded mounted video count: ${maxVideos}`);
    metrics.push({ name: 'video-unmount-max-mounted', ok: true, max_videos: maxVideos });
  });
  await memorySnapshot('after_video_filter');

  await runCommand('/media-all');
  if (firstItem.artist) await searchLatency(`a:${firstItem.artist}`, 'artist');
  if (firstItem.platform) await searchLatency(`p:${firstItem.platform}`, 'platform');
  if (Array.isArray(firstItem.topics) && firstItem.topics[0]) await searchLatency(`t:${firstItem.topics[0]}`, 'topic');

  await measure('logs-navigation', async () => {
    await (await browser.$('button=App Logs')).click();
    await waitFor(async () => browser.execute(() => document.body.innerText.includes('App Logs')));
  });

  await measure('settings-navigation', async () => {
    await (await browser.$('button=Settings')).click();
    await waitFor(async () => browser.execute(() => document.body.innerText.includes('System Settings')));
  });
}

function killProcessTree(processHandle) {
  if (!processHandle || processHandle.exitCode !== null) return;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(processHandle.pid)], { stdio: 'ignore', windowsHide: true });
  } else {
    processHandle.kill();
  }
}

async function cleanup() {
  try {
    if (browser) await browser.deleteSession();
  } catch {}
  killProcessTree(tauriDriverProcess);
  killProcessTree(backendProcess);
}

try {
  await runPerf();
  await writeResults(true);
  await cleanup();
  console.log(JSON.stringify({ ok: true, metrics, memory: memorySamples }, null, 2));
} catch (error) {
  await writeResults(false, error);
  await cleanup();
  console.error(error);
  process.exit(1);
}
