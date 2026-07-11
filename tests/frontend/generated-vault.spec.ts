import { expect, test, type Page, type Route } from '@playwright/test';
import manifestData from '../generated/001-playwright-scale/manifest.json';
import { installAppStateRoutes, makeAppSettings } from './app-state-fixture';

type GeneratedItem = {
  hash: string;
  storage_id: string;
  artist: string;
  platform: string;
  source_url: string;
  date_added: string;
  mime_type: string;
  extension: string;
  original_filename: string;
  width: number;
  height: number;
  topics: string[];
  url: string;
  thumbnail_url: string;
};

const SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#1f2937"/><text x="24" y="124" fill="#fff">LMZ</text></svg>';

let items: GeneratedItem[] = [];
let itemRequestCount = 0;

test.beforeAll(() => {
  items = (manifestData as { items: GeneratedItem[] }).items;
});

function facetItems(source: GeneratedItem[], key: keyof GeneratedItem | 'topic') {
  const counts = new Map<string, number>();
  for (const item of source) {
    const values = key === 'topic' ? item.topics : [String(item[key] || '')];
    for (const raw of values) {
      const value = String(raw || '').trim();
      if (value) counts.set(value, (counts.get(value) || 0) + 1);
    }
  }
  return [...counts.entries()].map(([value, count]) => ({ value, count }));
}

function filteredItems(url: URL) {
  const mediaType = url.searchParams.get('media_type') || 'all';
  const artists = url.searchParams.getAll('artist').map((value) => value.toLowerCase());
  const platforms = url.searchParams.getAll('platform').map((value) => value.toLowerCase());
  const topics = url.searchParams.getAll('topic').map((value) => value.toLowerCase());
  const texts = url.searchParams.getAll('text').map((value) => value.toLowerCase());

  return items.filter((item) => {
    if (mediaType === 'image' && !item.mime_type.startsWith('image/')) return false;
    if (mediaType === 'video' && !item.mime_type.startsWith('video/')) return false;
    if (artists.length && !artists.includes(item.artist.toLowerCase())) return false;
    if (platforms.length && !platforms.includes(item.platform.toLowerCase())) return false;
    if (topics.length && !topics.every((topic) => item.topics.map((value) => value.toLowerCase()).includes(topic))) return false;
    if (texts.length) {
      const haystack = `${item.hash} ${item.storage_id} ${item.artist} ${item.platform} ${item.source_url} ${item.topics.join(' ')}`.toLowerCase();
      if (!texts.every((text) => haystack.includes(text))) return false;
    }
    return true;
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installGeneratedApi(page: Page) {
  itemRequestCount = 0;
  await page.route('**/api/items**', async (route) => {
    itemRequestCount += 1;
    const url = new URL(route.request().url());
    const source = filteredItems(url);
    const start = Number(url.searchParams.get('cursor') || 0);
    const limit = Math.max(1, Math.min(Number(url.searchParams.get('limit') || 50), 100000));
    const end = Math.min(source.length, start + limit);
    return fulfillJson(route, {
      items: source.slice(start, end),
      has_more: end < source.length,
      next_cursor: end < source.length ? String(end) : null
    });
  });
  const settings = makeAppSettings('masonry');
  settings.ui.inspector_width = 380;
  await installAppStateRoutes(page, settings);
  await page.route('**/api/stats', async (route) => fulfillJson(route, { total_items: items.length }));
  await page.route('**/api/session-key', async (route) => fulfillJson(route, { key: 'generated-key' }));
  await page.route('**/api/queue-stats', async (route) => fulfillJson(route, { normal: 0, force: 0, failed: 0 }));
  await page.route('**/api/review/count', async (route) => fulfillJson(route, { count: 8, pending: 8, cleanup: 0 }));
  await page.route('**/api/system/memory', async (route) => fulfillJson(route, { backend_mb: 0 }));
  await page.route('**/api/logs/ui', async (route) => fulfillJson(route, { status: 'ok' }));
  await page.route('**/api/facets**', async (route) => {
    const kind = new URL(route.request().url()).searchParams.get('kind') || 'artist';
    const key = kind === 'topic' ? 'topic' : kind === 'platform' ? 'platform' : 'artist';
    return fulfillJson(route, { kind, items: facetItems(items, key as keyof GeneratedItem | 'topic') });
  });
  await page.route('**/api/search/suggestions**', async (route) => {
    const url = new URL(route.request().url());
    const kind = url.searchParams.get('kind') || 'artist';
    const query = (url.searchParams.get('q') || '').toLowerCase();
    const key = kind === 'topic' ? 'topic' : kind === 'platform' ? 'platform' : 'artist';
    const suggestions = facetItems(items, key as keyof GeneratedItem | 'topic')
      .filter((entry) => entry.value.toLowerCase().includes(query))
      .slice(0, 10);
    return fulfillJson(route, { kind, items: suggestions });
  });
  await page.route('**/api/thumbnails/**', async (route) => route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SVG }));
  await page.route('**/vault/**/*.jpg', async (route) => route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SVG }));
  await page.route('**/vault/**/*.mp4', async (route) => route.fulfill({ status: 204, body: '' }));
}

async function openGeneratedVault(page: Page) {
  await installGeneratedApi(page);
  await page.goto('/?lmz_test_page_size=120');
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();
  await expect(page.locator('.bottom-status')).toContainText(`Total Items: ${items.length}`);
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

async function assertRenderer(page: Page, layout: 'masonry' | 'grid') {
  const itemSelector = layout === 'masonry' ? 'masonry-renderer-item' : 'grid-renderer-item';
  const rendererItems = page.getByTestId(itemSelector);
  await expect(rendererItems.first()).toBeVisible();
  await expect.poll(async () => rendererItems.count()).toBeGreaterThan(0);

  const mounted = await page.getByTestId('vault-tile').count();
  expect(mounted).toBeGreaterThan(0);
  expect(mounted).toBeLessThan(300);

  const surface = await page.getByTestId('virtual-surface').evaluate((node) => {
    const el = node as HTMLElement;
    return {
      height: Number.parseFloat(el.style.height || '0'),
      scrollHeight: el.scrollHeight
    };
  });
  expect(Number.isFinite(surface.height)).toBeTruthy();
  expect(surface.height).toBeGreaterThan(1000);
  expect(surface.scrollHeight).toBeGreaterThan(1000);
  await assertNoOverlap(page, itemSelector);
}

async function scrollAndAssert(page: Page, layout: 'masonry' | 'grid') {
  const scroller = page.getByTestId('virtual-scroller');
  for (const ratio of [0, 0.5, 1]) {
    await scroller.evaluate((node, nextRatio) => {
      const el = node as HTMLElement;
      el.scrollTop = (el.scrollHeight - el.clientHeight) * Number(nextRatio);
      el.dispatchEvent(new Event('scroll'));
    }, ratio);
    await page.waitForTimeout(120);
    await assertRenderer(page, layout);
  }
}

async function runCommand(page: Page, command: string) {
  await page.getByTestId('vault-search-input').fill(command);
  await page.getByTestId('vault-search-input').press('Enter');
}

test('generated vault renders, filters, and handles synthetic videos', async ({ page }) => {
  await openGeneratedVault(page);

  const mounted = await page.getByTestId('vault-tile').count();
  expect(mounted).toBeGreaterThan(0);
  expect(mounted).toBeLessThan(300);

  const artist = items.find((item) => item.artist === 'artist-001')?.artist || items[0].artist;
  await runCommand(page, `a:${artist}`);
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();
  await expect(page.getByTestId('vault-tile').first()).toContainText(artist);

  await runCommand(page, '/media-video');
  await expect(page.locator('[data-testid="vault-tile"] video').first()).toBeVisible();
  const video = page.locator('[data-testid="vault-tile"] video').first();
  await expect(video).toHaveAttribute('src', /\/vault\/[a-f0-9]{2}\/lmz\d{6}\.mp4/);
  await expect(video).toHaveAttribute('poster', /\/api\/thumbnails\/[a-f0-9]{64}/);

  await runCommand(page, '/grid');
  await expect(page.getByTestId('grid-renderer-item').first()).toBeVisible();
});

test('generated vault scrolls in masonry and grid without unbounded mounting or overlap', async ({ page }) => {
  await openGeneratedVault(page);
  await scrollAndAssert(page, 'masonry');

  await runCommand(page, '/grid');
  await expect(page.getByTestId('grid-renderer-item').first()).toBeVisible();
  await scrollAndAssert(page, 'grid');
});

test('generated vault scroll loads additional pages through cursor pagination', async ({ page }) => {
  await openGeneratedVault(page);
  const initialRequests = itemRequestCount;
  const scroller = page.getByTestId('virtual-scroller');

  await scroller.evaluate((node) => {
    const el = node as HTMLElement;
    el.scrollTop = el.scrollHeight;
    el.dispatchEvent(new Event('scroll'));
  });

  await expect.poll(() => itemRequestCount).toBeGreaterThan(initialRequests);
  await expect(page.locator('.bottom-status')).toContainText(`Total Items: ${items.length}`);
});

test('generated vault supports manifest-backed platform topic and media filters', async ({ page }) => {
  await openGeneratedVault(page);

  const platform = items.find((item) => item.platform === 'pixiv')?.platform || items[0].platform;
  await runCommand(page, `p:${platform}`);
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();

  const topic = items[0].topics[0];
  await runCommand(page, `t:${topic}`);
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();

  await runCommand(page, '/media-image');
  await expect(page.locator('[data-testid="vault-tile"] img').first()).toBeVisible();
  await expect(page.locator('[data-testid="vault-tile"] video')).toHaveCount(0);
});

test('generated grouped media tiles expose navigation controls', async ({ page }) => {
  await openGeneratedVault(page);

  const groupedTile = page.locator('[data-testid="vault-tile"]').filter({ hasText: /1 \/ [2-9]/ }).first();
  await expect(groupedTile).toBeVisible();
  await expect(groupedTile).toContainText(/1 \/ [2-9]/);
  await groupedTile.getByRole('button', { name: 'Next Item' }).click();
  const advancedTile = page.locator('[data-testid="vault-tile"]').filter({ hasText: /2 \/ [2-9]/ }).first();
  await expect(advancedTile).toBeVisible();
  await advancedTile.getByRole('button', { name: 'Previous Item' }).click();
  await expect(page.locator('[data-testid="vault-tile"]').filter({ hasText: /1 \/ [2-9]/ }).first()).toBeVisible();
});
