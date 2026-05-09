import { expect, test, type Page, type Route } from '@playwright/test';

type LayoutMode = 'masonry' | 'grid';
type Scenario = 'single' | 'grouped';

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#161b22"/><rect x="24" y="24" width="272" height="192" fill="#30363d"/></svg>`;

function itemHash(index: number) {
  return index.toString(16).padStart(64, '0');
}

function makeItem(index: number, scenario: Scenario) {
  const hash = itemHash(index);
  const isVideo = index % 11 === 0;
  const grouped = scenario === 'grouped' && index % 4 !== 0;
  const groupId = Math.floor(index / 4);
  const width = 240 + (index % 5) * 40;
  const height = 180 + (index % 7) * 35;
  return {
    hash,
    extension: isVideo ? '.mp4' : '.jpg',
    mime_type: isVideo ? 'video/mp4' : 'image/jpeg',
    original_filename: `mock-${index}.${isVideo ? 'mp4' : 'jpg'}`,
    source_url: grouped ? `https://mock.local/group/${groupId}` : '',
    date_added: new Date(Date.UTC(2026, 0, 1, 0, 0, index % 60)).toISOString(),
    platform: index % 3 === 0 ? 'pixiv' : 'local',
    artist: `artist-${index % 23}`,
    url: isVideo ? `/mock/video/${hash}.mp4` : `/mock/full/${hash}.jpg`,
    thumbnail_url: `/mock/thumb/${hash}.svg`,
    width,
    height
  };
}

function parseStart(url: URL) {
  const cursor = url.searchParams.get('cursor');
  if (!cursor) return 0;
  const value = Number(cursor);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

async function installMockApi(page: Page, options: { total: number; layout: LayoutMode; scenario?: Scenario }) {
  const scenario = options.scenario || 'single';

  await page.route('**/api/items**', async (route: Route) => {
    const url = new URL(route.request().url());
    const limit = Math.max(1, Math.min(Number(url.searchParams.get('limit') || 50), 100000));
    const start = parseStart(url);
    const end = Math.min(options.total, start + limit);
    const items = [];
    for (let index = start; index < end; index += 1) items.push(makeItem(index, scenario));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items,
        has_more: end < options.total,
        next_cursor: end < options.total ? String(end) : null
      })
    });
  });

  await page.route('**/api/config', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success' }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ui: {
          vault_layout_mode: options.layout,
          vault_tile_min_width: 190,
          inspector_width: 400,
          ram_track_enabled: false
        }
      })
    });
  });

  await page.route('**/api/session-key', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ key: 'test-key' }) });
  });
  await page.route('**/api/stats', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total_items: options.total }) });
  });
  await page.route('**/api/queue-stats', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ normal: 0, force: 0, failed: 0 }) });
  });
  await page.route('**/api/review/count', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ count: 0, pending: 0, cleanup: 0 }) });
  });
  await page.route('**/api/system/memory', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ backend_mb: 0 }) });
  });
  await page.route('**/api/logs/ui', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
  });
  await page.route('**/mock/thumb/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SVG });
  });
  await page.route('**/mock/full/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SVG });
  });
  await page.route('**/mock/video/**', async (route) => {
    await route.fulfill({ status: 204, body: '' });
  });
}

async function openLargeVault(page: Page, options: { total: number; layout: LayoutMode; scenario?: Scenario }) {
  await installMockApi(page, options);
  await page.goto(`/?lmz_test_page_size=${options.total}`);
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();
  await expect(page.locator('.bottom-status')).toContainText(`Total Items: ${options.total}`);
}

async function assertRenderer(page: Page, layout: LayoutMode, total: number) {
  const itemSelector = layout === 'masonry' ? 'masonry-renderer-item' : 'grid-renderer-item';
  const rendererItems = page.getByTestId(itemSelector);
  await expect(rendererItems.first()).toBeVisible();
  await expect.poll(async () => rendererItems.count()).toBeGreaterThan(0);

  const mounted = await page.getByTestId('vault-tile').count();
  expect(mounted).toBeGreaterThan(0);
  expect(mounted).toBeLessThan(300);

  const surfaceHeight = await page.getByTestId('virtual-surface').evaluate((node) => {
    const height = Number.parseFloat((node as HTMLElement).style.height || '0');
    return { height, scrollHeight: (node as HTMLElement).scrollHeight };
  });
  expect(Number.isFinite(surfaceHeight.height)).toBeTruthy();
  expect(surfaceHeight.height).toBeGreaterThan(1000);
  expect(surfaceHeight.scrollHeight).toBeGreaterThan(1000);

  await assertNoOverlap(page, itemSelector);
  await expect(page.locator('.bottom-status')).toContainText(`Total Items: ${total}`);
}

async function assertNoOverlap(page: Page, testId: string) {
  const boxes = await page.getByTestId(testId).evaluateAll((nodes) => nodes.map((node) => {
    const rect = (node as HTMLElement).getBoundingClientRect();
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
  }).filter((box) => box.width > 1 && box.height > 1));

  const tolerance = 2;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      const horizontal = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const vertical = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      expect(horizontal > tolerance && vertical > tolerance, `visible item overlap: ${i}/${j}`).toBeFalsy();
    }
  }
}

async function scrollAndAssert(page: Page, layout: LayoutMode, total: number) {
  const scroller = page.getByTestId('virtual-scroller');
  for (const ratio of [0, 0.5, 1]) {
    await scroller.evaluate((node, nextRatio) => {
      const el = node as HTMLElement;
      el.scrollTop = (el.scrollHeight - el.clientHeight) * Number(nextRatio);
      el.dispatchEvent(new Event('scroll'));
    }, ratio);
    await page.waitForTimeout(120);
    await assertRenderer(page, layout, total);
  }

  const before = await page.getByTestId('vault-tile').count();
  for (const ratio of [0.2, 0.8, 0.35, 0.95]) {
    await scroller.evaluate((node, nextRatio) => {
      const el = node as HTMLElement;
      el.scrollTop = (el.scrollHeight - el.clientHeight) * Number(nextRatio);
      el.dispatchEvent(new Event('scroll'));
    }, ratio);
    await page.waitForTimeout(80);
  }
  const after = await page.getByTestId('vault-tile').count();
  expect(after).toBeLessThan(300);
  expect(Math.abs(after - before)).toBeLessThan(220);
}

for (const total of [10_000, 100_000]) {
  for (const layout of ['masonry', 'grid'] as const) {
    test(`${layout} handles ${total.toLocaleString()} single-item groups`, async ({ page }) => {
      await openLargeVault(page, { total, layout });
      await scrollAndAssert(page, layout, total);
    });
  }
}

test('mixed grouped media stays bounded and can switch layout', async ({ page }) => {
  await openLargeVault(page, { total: 10_000, layout: 'masonry', scenario: 'grouped' });
  await scrollAndAssert(page, 'masonry', 10_000);

  await page.getByTestId('vault-search-input').fill('/grid');
  await page.getByTestId('vault-search-input').press('Enter');
  await expect(page.getByTestId('grid-renderer-item').first()).toBeVisible();
  await scrollAndAssert(page, 'grid', 10_000);
});
