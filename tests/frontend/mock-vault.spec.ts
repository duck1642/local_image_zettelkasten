import { expect, test, type Page, type Route } from '@playwright/test';
import manifestData from '../fixtures/mock-vault/manifest.json';

type MockItem = {
  hash: string;
  artist: string;
  platform: string;
  source_url: string;
  url: string;
  thumbnail_url: string;
  [key: string]: unknown;
};

const manifest = manifestData as {
  items: MockItem[];
  review: unknown[];
  queues: Record<string, string[]>;
  expectations: Record<string, string | number>;
};

function cloneItems() {
  return manifest.items.map((item) => ({ ...item }));
}

function facetItems(items: MockItem[], key: string) {
  const counts = new Map<string, number>();
  for (const item of items) {
    const value = String(item[key] || '').trim();
    if (value) counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts.entries()].map(([value, count]) => ({ value, count }));
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installMockVaultApi(
  page: Page,
  options: {
    memoryFails?: boolean;
    onReviewAction?: () => Promise<void>;
    onLocalIngestStart?: () => Promise<void> | void;
    onMaintenanceAction?: (action: 'auth' | 'metadata' | 'review') => Promise<void> | void;
    metadataRebuildResponse?: unknown;
    metadataStatusSequence?: unknown[];
  } = {}
) {
  let items = cloneItems();
  const reviewItems = JSON.parse(JSON.stringify(manifest.review));
  const queueContent: Record<string, string> = {
    normal: manifest.queues.normal.join('\n'),
    force: manifest.queues.force.join('\n'),
    failed: manifest.queues.failed.join('\n')
  };
  const localStatus = {
    running: false,
    phase: 'idle',
    run_id: null,
    scanned: 0,
    staged: 0,
    queued: 0,
    processed: 0,
    summary: { ingested: 0, review: 0, failed: 0, duplicate: 0 },
    results: [],
    failed_paths: [],
    last_defaults: {},
    last_skip_similarity: false,
    started_at: null,
    finished_at: null,
    stop_requested: false
  };
  let metadataStatusIndex = 0;
  const appConfig = {
    ui: {
      vault_layout_mode: 'masonry',
      vault_tile_min_width: 190,
      inspector_width: 360,
      inspector_visible: true,
      ram_track_enabled: true
    }
  };

  await page.route('**/api/items**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const detailMatch = url.pathname.match(/\/api\/items\/([a-f0-9]{64})(?:\/.*)?$/);
    if (detailMatch) {
      const hash = detailMatch[1];
      const item = items.find((entry) => entry.hash === hash);
      if (!item) return fulfillJson(route, { detail: 'not found' }, 404);
      if (request.method() === 'PATCH') {
        const patch = JSON.parse(request.postData() || '{}');
        items = items.map((entry) => entry.hash === hash ? { ...entry, ...patch } : entry);
        return fulfillJson(route, { status: 'success' });
      }
      return fulfillJson(route, item);
    }

    const limit = Math.max(1, Math.min(Number(url.searchParams.get('limit') || 50), 100000));
    return fulfillJson(route, {
      items: items.slice(0, limit),
      has_more: items.length > limit,
      next_cursor: items.length > limit ? String(limit) : null
    });
  });

  await page.route('**/api/config', async (route) => fulfillJson(route, appConfig));
  await page.route('**/api/session-key', async (route) => fulfillJson(route, { key: 'mock-key' }));
  await page.route('**/api/stats', async (route) => fulfillJson(route, { total_items: items.length }));
  await page.route('**/api/logs**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' });
  });
  await page.route('**/api/queue/actions/retry-failed', async (route) => fulfillJson(route, {
    status: 'success',
    moved: 0,
    counts: {
      normal: manifest.queues.normal.length,
      force: manifest.queues.force.length,
      failed: manifest.queues.failed.length
    }
  }));
  await page.route('**/api/queue/actions/clear-failed', async (route) => fulfillJson(route, {
    status: 'success',
    counts: {
      normal: manifest.queues.normal.length,
      force: manifest.queues.force.length,
      failed: 0
    }
  }));
  await page.route('**/api/queue/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const match = url.pathname.match(/\/api\/queue\/([^/]+)/);
    if (!match) return fulfillJson(route, { detail: 'not found' }, 404);
    const queueName = match[1];
    if (!(queueName in queueContent)) return fulfillJson(route, { detail: 'invalid queue' }, 400);
    if (request.method() === 'GET') {
      const content = queueContent[queueName];
      const count = content.split('\n').filter((line) => line.trim().startsWith('http')).length;
      return fulfillJson(route, { content, count });
    }
    if (request.method() === 'POST') {
      const payload = JSON.parse(request.postData() || '{}');
      queueContent[queueName] = String(payload.content || '');
      const count = queueContent[queueName].split('\n').filter((line) => line.trim().startsWith('http')).length;
      return fulfillJson(route, { status: 'success', count });
    }
    return fulfillJson(route, { status: 'ok' });
  });
  await page.route('**/api/queue-stats', async (route) => fulfillJson(route, {
    normal: manifest.queues.normal.length,
    force: manifest.queues.force.length,
    failed: manifest.queues.failed.length
  }));
  await page.route('**/api/review/count', async (route) => fulfillJson(route, { count: reviewItems.length, pending: 1, cleanup: 1 }));
  await page.route('**/api/review/cleanup', async (route) => {
    await options.onMaintenanceAction?.('review');
    return fulfillJson(route, { status: 'success', cleaned: 0, failed: 0, cleaned_orphans: 0, failed_orphans: 0 });
  });
  await page.route('**/api/metadata-index/rebuild', async (route) => {
    await options.onMaintenanceAction?.('metadata');
    return fulfillJson(route, options.metadataRebuildResponse || { status: 'started' });
  });
  await page.route('**/api/metadata-index/status', async (route) => {
    const sequence = options.metadataStatusSequence || [];
    const body = sequence[Math.min(metadataStatusIndex, Math.max(0, sequence.length - 1))] || {
      ready: true,
      repair_running: false,
      items: items.length,
      indexed: items.length,
      errors: 0,
      dirty: 0,
      maintenance_rebuild: { running: false, status: 'idle' }
    };
    metadataStatusIndex += 1;
    return fulfillJson(route, body);
  });
  await page.route('**/api/review/*/action**', async (route) => {
    await options.onReviewAction?.();
    return fulfillJson(route, { status: 'success', action: 'keep', message: 'mock action ok' });
  });
  await page.route('**/api/review', async (route) => fulfillJson(route, reviewItems));
  await page.route('**/api/facets**', async (route) => {
    const kind = new URL(route.request().url()).searchParams.get('kind') || 'artist';
    const key = kind === 'wd_tag' ? 'artist' : kind;
    return fulfillJson(route, { kind, items: facetItems(items, key) });
  });
  await page.route('**/api/system/memory', async (route) => {
    if (options.memoryFails) return fulfillJson(route, { detail: 'unavailable' }, 500);
    return fulfillJson(route, { backend_mb: 42.5 });
  });
  await page.route('**/api/auth/scan', async (route) => {
    await options.onMaintenanceAction?.('auth');
    return fulfillJson(route, { status: 'ok', auth: { cookies: 'available' } });
  });
  await page.route('**/api/local-ingest/status', async (route) => fulfillJson(route, localStatus));
  await page.route('**/api/local-ingest/start', async (route) => {
    await options.onLocalIngestStart?.();
    return fulfillJson(route, { status: 'success', run_id: 'mock-run', phase: 'scanning' });
  });
  await page.route('**/api/local-ingest/retry-failed', async (route) => fulfillJson(route, { status: 'success', queued: 0, phase: 'idle' }));
  await page.route('**/api/local-ingest/drop-intake', async (route) => fulfillJson(route, { detail: 'unused in browser mock' }, 404));
  await page.route('**/api/logs/ui', async (route) => fulfillJson(route, { status: 'ok' }));
  await page.route('**/mock-vault/assets/**', async (route) => {
    const assetName = new URL(route.request().url()).pathname.split('/').pop() || 'mock.svg';
    await route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#1f2937"/><text x="24" y="124" fill="#fff">${assetName.slice(0, 6)}</text></svg>`
    });
  });
  await page.route('**/mock-vault/video/**', async (route) => {
    await route.fulfill({ status: 204, body: '' });
  });
  await page.route('**/review-assets/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180"><rect width="240" height="180" fill="#334155"/><text x="24" y="96" fill="#fff">Review</text></svg>'
    });
  });
}

async function openMockVault(
  page: Page,
  options: {
    memoryFails?: boolean;
    onReviewAction?: () => Promise<void>;
    onLocalIngestStart?: () => Promise<void> | void;
    onMaintenanceAction?: (action: 'auth' | 'metadata' | 'review') => Promise<void> | void;
  } = {}
) {
  await installMockVaultApi(page, options);
  await page.goto('/?lmz_test_page_size=100');
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();
  await expect(page.locator('.bottom-status')).toContainText('Total Items: 3');
}

test('mock vault fixture is isolated and renders grouped media paths', async ({ page }) => {
  await openMockVault(page);

  await expect(page.locator('.bottom-status')).toContainText('Showing 2 groups');
  await expect(page.getByText('Mock Solo')).toBeVisible();
  await expect(page.getByText('Mock Group B')).toBeVisible();
  await page.getByText('Mock Group B').click();
  await page.locator('aside.inspector .group-nav button').last().click();
  await expect(page.locator('aside.inspector video')).toHaveAttribute('src', /mock-vault\/video/);
});

test('artist edit refreshes tile while source URL and platform stay read-only', async ({ page }) => {
  await openMockVault(page);

  await page.getByText('Mock Solo').click();
  await expect(page.getByLabel('Artist')).toHaveValue('Mock Solo');
  await expect(page.getByLabel('Source URL')).toHaveAttribute('readonly', '');
  await expect(page.locator('aside.inspector')).toContainText('Platform');
  await expect(page.locator('aside.inspector input#inspector-platform')).toHaveCount(0);
  await page.getByLabel('Artist').fill(String(manifest.expectations.editedArtist));
  await page.getByRole('button', { name: 'Save Changes' }).click();

  await expect(page.getByText(String(manifest.expectations.editedArtist))).toBeVisible();
  await expect(page.getByLabel('Artist')).toHaveValue(String(manifest.expectations.editedArtist));
  await expect(page.locator('.bottom-status')).toContainText(`Showing ${manifest.expectations.initialGroups} groups`);
});

test('masonry keeps current data after metadata update cache reuse', async ({ page }) => {
  await openMockVault(page);

  await page.getByText('Mock Solo').click();
  await page.getByLabel('Artist').fill('Cache Fresh Artist');
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await page.getByTestId('virtual-scroller').evaluate((node) => {
    const el = node as HTMLElement;
    el.scrollTop = 200;
    el.dispatchEvent(new Event('scroll'));
    el.scrollTop = 0;
    el.dispatchEvent(new Event('scroll'));
  });

  await expect(page.getByText('Cache Fresh Artist')).toBeVisible();
  await expect(page.getByText('Mock Solo')).toHaveCount(0);
});

test('fullscreen pan suppresses one backdrop click then closes after reset', async ({ page }) => {
  await openMockVault(page);

  await page.getByText('Mock Solo').click();
  await page.getByTitle('Fullscreen').click({ force: true });
  await expect(page.locator('.focus-overlay.fullscreen')).toBeVisible();

  const frame = page.locator('.media-frame');
  await frame.dispatchEvent('wheel', { deltaY: -180, ctrlKey: true, clientX: 400, clientY: 300 });
  const box = await frame.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2 + 40, box!.y + box!.height / 2 + 20);
  await page.mouse.up();
  await page.locator('.focus-overlay.fullscreen').dispatchEvent('click');
  await expect(page.locator('.focus-overlay.fullscreen')).toBeVisible();

  for (let i = 0; i < 10; i += 1) {
    await frame.dispatchEvent('wheel', { deltaY: 240, ctrlKey: true, clientX: 400, clientY: 300 });
  }
  await page.waitForTimeout(150);
  await page.locator('.focus-overlay.fullscreen').dispatchEvent('click');
  await expect(page.locator('.focus-overlay.fullscreen')).toHaveCount(0);
});

test('fullscreen uses browser fallback when native fullscreen is unavailable', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, '__TAURI_INTERNALS__', {
      configurable: true,
      get: () => undefined,
      set: () => {}
    });
    let fullscreenElement: Element | null = null;
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fullscreenElement
    });
    Object.defineProperty(Element.prototype, 'requestFullscreen', {
      configurable: true,
      value: async () => {
        (window as any).__browserFsRequests = ((window as any).__browserFsRequests || 0) + 1;
        fullscreenElement = document.documentElement;
      }
    });
    Object.defineProperty(Document.prototype, 'exitFullscreen', {
      configurable: true,
      value: async () => {
        (window as any).__browserFsExits = ((window as any).__browserFsExits || 0) + 1;
        fullscreenElement = null;
      }
    });
  });
  await openMockVault(page);

  await page.getByText('Mock Solo').click();
  await page.getByTitle('Fullscreen').click({ force: true });
  await expect(page.locator('.focus-overlay.fullscreen')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).__browserFsRequests || 0)).toBe(1);
  await page.keyboard.press('Escape');
  await expect(page.locator('.focus-overlay.fullscreen')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as any).__browserFsExits || 0)).toBeGreaterThanOrEqual(1);
});

test('review fixture uses display names and encoded asset/action paths', async ({ page }) => {
  const reviewRequests: string[] = [];
  await openMockVault(page);
  page.on('request', (request) => {
    if (request.url().includes('/api/review/') || request.url().includes('/review-assets/')) {
      reviewRequests.push(request.url());
    }
  });

  await page.getByRole('button', { name: /Review/ }).click();
  await expect(page.getByRole('button', { name: 'Original Review Name.jpg pending' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Locked Cleanup Item\.jpg/ })).toBeVisible();
  await page.getByRole('button', { name: /Original Review Name\.jpg/ }).click();
  await page.getByRole('button', { name: 'Keep Visible' }).click();

  expect(reviewRequests.some((url) => url.includes('review%2520encoded%2Bname.jpg'))).toBeTruthy();
});

test('review destructive actions unmount media before posting', async ({ page }) => {
  let mediaUnmountedBeforePost = false;
  await openMockVault(page, {
    onReviewAction: async () => {
      mediaUnmountedBeforePost = await page.locator('.review-main .pane img, .review-main .pane video').count() === 0;
    }
  });

  await page.getByRole('button', { name: /Review/ }).click();
  await page.getByRole('button', { name: /Original Review Name\.jpg/ }).click();
  await expect(page.locator('.review-main .pane img')).toHaveCount(2);
  await page.getByRole('button', { name: 'Save Variant' }).click();

  await expect.poll(() => mediaUnmountedBeforePost).toBeTruthy();
});

test('drop request switches to local mode and appends deduped staged paths', async ({ page }) => {
  let localStartCalls = 0;
  await openMockVault(page, {
    onLocalIngestStart: () => {
      localStartCalls += 1;
    }
  });

  await page.getByRole('button', { name: /Ingestion/ }).click();
  await expect(page.getByRole('button', { name: 'Start Ingestion' })).toBeVisible();

  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('lmz:test-drop-request', {
      detail: {
        id: 'drop-1',
        session_id: 'session-1',
        source_tab: 'vault',
        accepted_paths: ['C:/drop/a.jpg', 'C:/drop/a.jpg', 'C:/drop/folder'],
        skipped: [{ path: 'C:/drop/x.txt', reason: 'unsupported_extension' }],
        summary: { received: 4, accepted: 3, skipped: 1 }
      }
    }));
  });

  await expect(page.getByRole('button', { name: 'Start Local Ingestion' })).toBeVisible();
  await expect(page.locator('.local-item')).toHaveCount(2);
  await expect(page.locator('.local-item')).toContainText(['C:/drop/a.jpg', 'C:/drop/folder']);
  expect(localStartCalls).toBe(0);
});

test('drop request does not auto-start local ingestion', async ({ page }) => {
  let localStartCalls = 0;
  await openMockVault(page, {
    onLocalIngestStart: () => {
      localStartCalls += 1;
    }
  });

  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('lmz:test-drop-request', {
      detail: {
        id: 'drop-2',
        session_id: 'session-2',
        source_tab: 'vault',
        accepted_paths: ['C:/drop/b.jpg'],
        skipped: [],
        summary: { received: 1, accepted: 1, skipped: 0 }
      }
    }));
  });

  await expect(page.getByRole('button', { name: 'Start Local Ingestion' })).toBeVisible();
  expect(localStartCalls).toBe(0);
});

test('ram footer handles available and unavailable states', async ({ page }) => {
  await openMockVault(page);
  await expect(page.locator('.ram-status')).toContainText('RAM: backend 42.5 MB');

  const failingPage = await page.context().newPage();
  await openMockVault(failingPage, { memoryFails: true });
  await expect(failingPage.locator('.ram-status')).toContainText('RAM: unavailable');
  await failingPage.close();
});

test('settings maintenance actions call existing endpoints and show compact statuses', async ({ page }) => {
  const calls: Array<'auth' | 'metadata' | 'review'> = [];
  await openMockVault(page, {
    onMaintenanceAction: (action) => {
      calls.push(action);
    }
  });

  await page.getByRole('button', { name: /Settings/ }).click();
  await page.getByRole('button', { name: 'Auth Scan' }).click();
  await page.getByRole('button', { name: 'Rebuild Metadata Index' }).click();
  await page.getByRole('button', { name: 'Cleanup Review' }).click();

  await expect(page.locator('.maintenance-status')).toContainText(['OK (available)', 'started', 'cleaned 0, failed 0']);
  expect(calls).toEqual(['auth', 'metadata', 'review']);
});

test('settings metadata rebuild shows progress only for maintenance job', async ({ page }) => {
  await openMockVault(page, {
    metadataRebuildResponse: {
      status: 'started',
      maintenance_rebuild: {
        running: true,
        status: 'running',
        stage: 'starting',
        items_total: 100,
        items_done: 0,
        errors: 0
      }
    },
    metadataStatusSequence: [
      {
        ready: false,
        repair_running: true,
        items: 100,
        indexed: 0,
        errors: 0,
        dirty: 0,
        maintenance_rebuild: {
          running: true,
          status: 'running',
          stage: 'reading metadata',
          items_total: 100,
          items_done: 40,
          errors: 0
        }
      },
      {
        ready: true,
        repair_running: false,
        items: 100,
        indexed: 100,
        errors: 0,
        dirty: 0,
        maintenance_rebuild: {
          running: false,
          status: 'completed',
          stage: 'completed',
          items_total: 100,
          items_done: 100,
          errors: 0,
          duration_ms: 1200
        }
      }
    ]
  });

  await page.getByRole('button', { name: /Settings/ }).click();
  await expect(page.getByLabel('Metadata rebuild progress')).toHaveCount(0);

  await page.getByRole('button', { name: 'Rebuild Metadata Index' }).click();
  await expect(page.getByLabel('Metadata rebuild progress')).toBeVisible();
  await expect(page.locator('.maintenance-status').nth(1)).toContainText('40 / 100');
  await expect(page.locator('.metadata-progress-fill')).toHaveAttribute('style', /40%/);
  await expect(page.locator('.maintenance-status').nth(1)).toContainText('completed', { timeout: 3000 });
  await expect(page.getByLabel('Metadata rebuild progress')).toHaveCount(0);
});
