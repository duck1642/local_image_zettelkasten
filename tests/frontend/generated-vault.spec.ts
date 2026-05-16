import { expect, test, type Page, type Route } from '@playwright/test';
import manifestData from '../generated/001-playwright-scale/manifest.json';

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
  await page.route('**/api/items**', async (route) => {
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
  await page.route('**/api/config', async (route) => {
    if (route.request().method() === 'POST') return fulfillJson(route, { status: 'success' });
    return fulfillJson(route, {
      ui: {
        vault_layout_mode: 'masonry',
        vault_tile_min_width: 190,
        inspector_width: 380,
        inspector_visible: true,
        ram_track_enabled: false
      }
    });
  });
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
  await page.goto('/?lmz_test_page_size=200');
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();
  await expect(page.locator('.bottom-status')).toContainText(`Total Items: ${items.length}`);
}

test('generated vault renders, filters, and handles synthetic videos', async ({ page }) => {
  await openGeneratedVault(page);

  const mounted = await page.getByTestId('vault-tile').count();
  expect(mounted).toBeGreaterThan(0);
  expect(mounted).toBeLessThan(300);

  const artist = items.find((item) => item.artist === 'artist-001')?.artist || items[0].artist;
  await page.getByTestId('vault-search-input').fill(`a:${artist}`);
  await page.getByTestId('vault-search-input').press('Enter');
  await expect(page.getByTestId('vault-tile').first()).toBeVisible();
  await expect(page.getByTestId('vault-tile').first()).toContainText(artist);

  await page.getByTestId('vault-search-input').fill('/media-video');
  await page.getByTestId('vault-search-input').press('Enter');
  await expect(page.locator('[data-testid="vault-tile"] video').first()).toBeVisible();
  const video = page.locator('[data-testid="vault-tile"] video').first();
  await expect(video).toHaveAttribute('src', /\/vault\/[a-f0-9]{2}\/lmz\d{6}\.mp4/);
  await expect(video).toHaveAttribute('poster', /\/api\/thumbnails\/[a-f0-9]{64}/);

  await page.getByTestId('vault-search-input').fill('/grid');
  await page.getByTestId('vault-search-input').press('Enter');
  await expect(page.getByTestId('grid-renderer-item').first()).toBeVisible();
});
