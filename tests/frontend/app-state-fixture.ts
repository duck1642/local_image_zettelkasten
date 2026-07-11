import type { Page, Route } from '@playwright/test';

export function makeAppSettings(layout: 'masonry' | 'grid' = 'masonry', tileWidth = 190) {
  return {
    schema_version: 1,
    ui: {
      vault_layout_mode: layout,
      vault_tile_min_width: tileWidth,
      inspector_visible: true,
      inspector_width: 400,
      privacy_blur: false,
      ram_tracking_enabled: false
    },
    webview: { devtools_enabled: false, context_menu_enabled: false },
    logging: { level: 'INFO' },
    network: { proxy: '', user_agent: 'LMZ/1.0' },
    ingestion: {
      concurrency: { global_max_workers: 10, platforms: {} },
      accepted_media: {
        extensions: ['.jpg', '.jpeg', '.png', '.webp', '.mp4'],
        mime_types: ['image/jpeg', 'image/png', 'image/webp', 'video/mp4']
      },
      processing: { flatten_transparency: true, background_preset: 'white', custom_color: [255, 255, 255] }
    },
    tagging: {
      enabled: true,
      model_repo: 'SmilingWolf/wd-vit-tagger-v3',
      device: 'auto',
      display_source: 'yaml',
      threshold: 0.35,
      max_tags: 30,
      fail_ingestion_on_error: false,
      video: { enabled: true, frame_count: 5, merge_min_frames: 2, merge_high_confidence: 0.75 }
    }
  };
}

export const loadedRuntimeSession = {
  loaded: true,
  workspace: { root: 'C:/ObsidianVault/lmz', topics_root: 'C:/ObsidianVault/lmz/data/topics' },
  vault: {
    id: 'default',
    name: 'Default',
    root: 'C:/ObsidianVault/lmz/data/vaults/default',
    database: 'C:/ObsidianVault/lmz/data/vaults/default/db/lmz_main.db'
  },
  env_override: false
};

async function fulfillJson(route: Route, body: unknown, headers: Record<string, string> = {}) {
  await route.fulfill({ status: 200, contentType: 'application/json', headers, body: JSON.stringify(body) });
}

export async function installAppStateRoutes(
  page: Page,
  initialSettings = makeAppSettings(),
  options: { putStatus?: number } = {}
) {
  let settings = structuredClone(initialSettings);
  let version = 1;
  await page.route('**/api/app/settings', async (route) => {
    if (route.request().method() === 'PUT') {
      if (options.putStatus && options.putStatus !== 200) {
        return route.fulfill({
          status: options.putStatus,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'App settings changed since they were loaded' })
        });
      }
      settings = JSON.parse(route.request().postData() || '{}');
      version += 1;
    }
    return fulfillJson(route, settings, { ETag: `"test-settings-${version}"` });
  });
  await page.route('**/api/runtime/session', async (route) => fulfillJson(route, loadedRuntimeSession));
}
