import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..', '..', '..');
const configPath = process.env.LMZ_PERF_CONFIG_PATH;
const backendUrl = process.env.LMZ_PERF_BACKEND_URL || 'http://127.0.0.1:8000';
let resultPath;
const metrics = [];

function nowMs() {
  return performance.now();
}

async function measure(name, fn) {
  const start = nowMs();
  const result = await fn();
  const durationMs = Math.round((nowMs() - start) * 100) / 100;
  metrics.push({ name, duration_ms: durationMs, ok: true });
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
    await browser.pause(intervalMs);
  }
  throw lastError || new Error('timed out waiting for condition');
}

async function waitBackend() {
  await waitFor(async () => {
    const response = await fetch(`${backendUrl}/api/session-key`);
    return response.ok;
  }, 60000, 350);
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
  const input = await $('[data-testid="vault-search-input"]');
  await input.setValue(command);
  await browser.keys('Enter');
}

async function writeResults(ok, error = null) {
  const runId = path.basename(path.dirname(configPath));
  const dir = path.join(rootDir, 'tests', 'perf-results', runId);
  fs.mkdirSync(dir, { recursive: true });
  resultPath = path.join(dir, 'tauri-webview.json');
  const summary = {
    kind: 'tauri-webview',
    run_id: runId,
    config_path: configPath,
    backend_url: backendUrl,
    ok,
    error: error ? String(error.stack || error) : null,
    metrics
  };
  fs.writeFileSync(resultPath, JSON.stringify(summary, null, 2));
}

describe('Tauri WebView performance', () => {
  before(async () => {
    await measure('backend-ready', async () => {
      await waitBackend();
    });
  });

  it('measures real app launch, scrolling, filters, and navigation', async () => {
    try {
      await measure('first-tile-visible', async () => {
        await waitFor(async () => {
          const tiles = await visibleTileCount();
          return tiles > 0;
        }, 90000);
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
        for (const [label, ratio] of [
          ['top', 0],
          ['middle', 0.5],
          ['bottom', 1]
        ]) {
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
        const logs = await $('button=App Logs');
        await logs.click();
        await waitFor(async () => (await browser.execute(() => document.body.innerText.includes('App Logs'))));
      });

      await measure('settings-navigation', async () => {
        const settings = await $('button=Settings');
        await settings.click();
        await waitFor(async () => (await browser.execute(() => document.body.innerText.includes('System Settings'))));
      });

      await writeResults(true);
    } catch (error) {
      await writeResults(false, error);
      throw error;
    }
  });
});
