import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, '$1'), '..');
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium, expect } = require('@playwright/test');

const workspace = path.resolve(process.argv[2] || path.join(root, 'tests/generated/010-smoke-maintenance'));
const screenshots = path.join(workspace, 'smoke-screens');
fs.mkdirSync(screenshots, { recursive: true });

const baseUrl = 'http://127.0.0.1:5173';
const apiBase = 'http://127.0.0.1:8000';
const report = { steps: [], artifacts: {} };
let backendProc = null;
let viteProc = null;

function record(step, data = {}) {
  report.steps.push({ step, ...data });
}

async function waitFor(url, timeoutMs = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function ensureBackend() {
  try {
    await waitFor(`${apiBase}/api/app/settings`, 1000);
    return;
  } catch {
    const out = fs.openSync(path.join(workspace, 'backend-smoke.out.log'), 'a');
    const err = fs.openSync(path.join(workspace, 'backend-smoke.err.log'), 'a');
    backendProc = spawn(process.platform === 'win32' ? 'python' : 'python3', ['web_api.py'], {
      cwd: path.join(root, 'backend'),
      env: {
        ...process.env,
        LMZ_CONFIG_PATH: path.join(workspace, 'config.yaml'),
        LMZ_DATA_ROOT: path.join(workspace, '.lmz-app'),
        LMZ_DISABLE_RELOAD: '1'
      },
      stdio: ['ignore', out, err],
      windowsHide: true
    });
    fs.writeFileSync(path.join(workspace, 'backend-smoke.pid'), String(backendProc.pid));
    await waitFor(`${apiBase}/api/app/settings`, 30000);
  }
}

async function ensureVite() {
  try {
    await waitFor(baseUrl, 1000);
    return;
  } catch {
    const out = fs.openSync(path.join(workspace, 'vite-smoke.out.log'), 'a');
    const err = fs.openSync(path.join(workspace, 'vite-smoke.err.log'), 'a');
    const viteCommand = process.platform === 'win32' ? 'cmd.exe' : 'npm';
    const viteArgs = process.platform === 'win32'
      ? ['/c', 'npm.cmd', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173']
      : ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173'];
    viteProc = spawn(viteCommand, viteArgs, {
      cwd: path.join(root, 'frontend'),
      stdio: ['ignore', out, err],
      windowsHide: true
    });
    fs.writeFileSync(path.join(workspace, 'vite-smoke.pid'), String(viteProc.pid));
    await waitFor(baseUrl, 30000);
  }
}

async function apiKey() {
  const response = await fetch(`${apiBase}/api/session-key`);
  if (!response.ok) throw new Error(`session key failed ${response.status}`);
  return (await response.json()).key || '';
}

async function apiJson(endpoint, init = {}) {
  const headers = new Headers(init.headers || {});
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(String(init.method || 'GET').toUpperCase())) {
    headers.set('X-LMZ-API-KEY', await apiKey());
  }
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${apiBase}${endpoint}`, { ...init, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${endpoint} failed ${response.status}: ${JSON.stringify(payload)}`);
  return payload;
}

async function shot(page, name) {
  const file = path.join(screenshots, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  report.artifacts[name] = file;
}

async function toastPath(page, title) {
  const toast = page.locator('.toast-card').filter({ hasText: title }).last();
  await expect(toast).toBeVisible({ timeout: 20000 });
  const text = await toast.innerText();
  const match = text.match(/created at:\s*(.+?)\.$/m);
  if (!match) throw new Error(`Could not parse package path from toast: ${text}`);
  return String(match[1]).trim();
}

async function openMaintenance(page) {
  await page.getByRole('button', { name: /Settings/ }).click();
  await page.getByRole('button', { name: 'Maintenance' }).click();
  await expect(page.getByText('Merge Vaults')).toBeVisible();
}

async function waitForMetadataRebuild() {
  const started = Date.now();
  let latest = null;
  while (Date.now() - started < 60000) {
    const payload = await apiJson('/api/metadata-index/status');
    latest = payload.maintenance_rebuild || null;
    if (latest && latest.running === false && ['completed', 'error'].includes(String(latest.status || ''))) {
      if (latest.status === 'error') throw new Error(`metadata rebuild failed: ${latest.message || 'unknown error'}`);
      return latest;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`metadata rebuild did not finish: ${JSON.stringify(latest)}`);
}

async function main() {
  await ensureBackend();
  await ensureVite();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on('dialog', (dialog) => dialog.accept());

  await page.goto(`${baseUrl}/?lmz_test_page_size=120`);
  await expect(page.locator('.bottom-status')).toContainText('Total Items: 80', { timeout: 30000 });
  await shot(page, '01-vault-loaded');

  await openMaintenance(page);
  await shot(page, '02-maintenance-start');

  await page.getByRole('button', { name: 'Scan' }).click();
  await expect(page.locator('.settings-action-row-status').first()).toContainText('X: missing', { timeout: 10000 });
  await expect(page.locator('.settings-action-row-status').first()).toContainText('Pixiv: missing');
  await shot(page, '02-auth-scan');
  record('auth scan', { ok: true });

  await page.getByRole('button', { name: 'Rebuild' }).click();
  const metadataJob = await waitForMetadataRebuild();
  await expect(page.locator('.settings-action-row-status').nth(1)).toContainText('completed', { timeout: 10000 });
  record('metadata rebuild', { ok: true, items_done: metadataJob.items_done || 0, errors: metadataJob.errors || 0 });

  await page.getByRole('button', { name: 'Audit' }).click();
  await expect(page.getByText(/Vault Health Check:/)).toBeVisible({ timeout: 30000 });
  const healthBeforeRepair = await apiJson('/api/vaults/default/health');
  if (healthBeforeRepair.issue_count !== 0) {
    throw new Error(`generated vault is unhealthy before repair: ${JSON.stringify({
      issue_count: healthBeforeRepair.issue_count,
      missing_files: healthBeforeRepair.missing_files,
      hash_mismatches: healthBeforeRepair.hash_mismatches?.length || 0,
      workspace_dictionary_drift: healthBeforeRepair.workspace_dictionary_drift
    })}`);
  }
  await shot(page, '03-health-audit');
  record('health audit', { ok: true, issue_count: healthBeforeRepair.issue_count });

  await page.getByRole('button', { name: 'Repair' }).click();
  await expect(page.getByRole('dialog', { name: 'Repair Vault' })).toBeVisible();
  await page.getByRole('dialog', { name: 'Repair Vault' }).getByRole('button', { name: 'Repair' }).click();
  await expect(page.getByText('Repair Complete')).toBeVisible({ timeout: 30000 });
  const healthAfterRepair = await apiJson('/api/vaults/default/health');
  if (healthAfterRepair.issue_count !== 0) {
    throw new Error(`generated vault is unhealthy after repair: ${JSON.stringify({
      issue_count: healthAfterRepair.issue_count,
      missing_files: healthAfterRepair.missing_files,
      hash_mismatches: healthAfterRepair.hash_mismatches?.length || 0,
      workspace_dictionary_drift: healthAfterRepair.workspace_dictionary_drift
    })}`);
  }
  await shot(page, '04-health-repair');
  record('health repair', { ok: true, issue_count: healthAfterRepair.issue_count });

  await page.getByRole('button', { name: 'Backup Vault Folder' }).click();
  await expect(page.getByRole('dialog', { name: 'Create Backup' })).toBeVisible();
  await shot(page, '05-backup-confirm');
  await page.getByRole('dialog', { name: 'Create Backup' }).getByRole('button', { name: 'Backup' }).click();
  const backupPath = await toastPath(page, 'Backup Successful');
  if (!fs.existsSync(backupPath)) throw new Error(`backup missing: ${backupPath}`);
  record('backup', { ok: true, path: backupPath });

  await page.getByRole('button', { name: 'Export Vault Package' }).click();
  await expect(page.getByRole('dialog', { name: 'Export Vault' })).toBeVisible();
  await page.getByLabel('Include review state').check();
  await shot(page, '06-export-confirm');
  await page.getByRole('dialog', { name: 'Export Vault' }).getByRole('button', { name: 'Export' }).click();
  const exportPath = await toastPath(page, 'Export Successful');
  if (!fs.existsSync(exportPath)) throw new Error(`export missing: ${exportPath}`);
  record('export', { ok: true, path: exportPath });

  await page.getByTestId('import-package-path').evaluate((node, value) => {
    node.value = value;
    node.dispatchEvent(new Event('input', { bubbles: true }));
  }, exportPath);
  await page.getByPlaceholder('Imported vault display name').fill('Imported Smoke');
  await page.locator('.vault-package-import-card').getByTitle('Preview').click();
  await expect(page.getByText('Package Preview Ready')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.import-preview-box')).toContainText('Target: imported-smoke');
  await shot(page, '07-import-preview');
  await page.locator('.vault-package-import-card').getByTitle('Import Vault').click();
  await expect(page.getByRole('dialog', { name: 'Import Vault' })).toBeVisible();
  const importResponsePromise = page.waitForResponse((response) =>
    response.url().includes('/api/vaults/import') && response.request().method() === 'POST',
    { timeout: 30000 }
  );
  await page.getByRole('dialog', { name: 'Import Vault' }).getByRole('button', { name: 'Import' }).click();
  const importResponse = await importResponsePromise;
  if (!importResponse.ok()) throw new Error(`import request failed ${importResponse.status()}: ${await importResponse.text()}`);
  await expect(page.locator('.toast-card').filter({ hasText: 'Vault Imported' })).toBeVisible({ timeout: 30000 });
  const vaultsAfterImport = await apiJson('/api/vaults');
  if (!vaultsAfterImport.items.some((vault) => vault.id === 'imported-smoke')) {
    throw new Error(`imported-smoke missing immediately after import: ${JSON.stringify(vaultsAfterImport.items)}`);
  }
  record('import export package', { ok: true, target: 'imported-smoke' });

  const restorePreview = await apiJson('/api/vaults/restore-preview', {
    method: 'POST',
    body: JSON.stringify({ package_path: backupPath })
  });
  const restoreResult = await apiJson('/api/vaults/restore', {
    method: 'POST',
    body: JSON.stringify({ package_path: backupPath, package_fingerprint: restorePreview.package_fingerprint, confirm: true })
  });
  const vaultsAfterRestore = await apiJson('/api/vaults');
  if (!vaultsAfterRestore.items.some((vault) => vault.id === 'imported-smoke')) {
    throw new Error(`restore dropped imported-smoke: ${JSON.stringify(vaultsAfterRestore.items)}`);
  }
  record('restore backup package', { ok: true, target: restoreResult.vault || restoreResult.name });

  await page.reload();
  await expect(page.locator('.bottom-status')).toContainText('Total Items: 80', { timeout: 30000 });
  await openMaintenance(page);
  await expect(page.locator('.merge-vault-row').filter({ hasText: 'Imported Smoke' })).toBeVisible({ timeout: 30000 });
  await shot(page, '08-vaults-after-import-restore');

  await page.getByLabel('Merged vault name').fill('Merged Smoke');
  await page.getByRole('checkbox', { name: /Default Active 80 items/ }).check();
  await page.locator('.merge-vault-row').filter({ hasText: 'Imported Smoke' }).getByRole('checkbox').check();
  const mergeSection = page.locator('.settings-section').filter({ hasText: 'Merge Vaults' });
  await mergeSection.getByRole('button', { name: 'Preview' }).click();
  await expect(page.locator('.merge-preview-box')).toContainText('Importable', { timeout: 30000 });
  await shot(page, '09-merge-preview');
  await mergeSection.getByRole('button', { name: 'Create' }).click();
  await expect(page.getByRole('dialog', { name: 'Merge Vaults' })).toBeVisible();
  await page.getByRole('dialog', { name: 'Merge Vaults' }).getByRole('button', { name: 'Create' }).click();
  await expect(page.getByText('Merged Vault Created')).toBeVisible({ timeout: 60000 });
  record('merge vaults', { ok: true, target: 'merged-smoke' });

  const vaults = await apiJson('/api/vaults');
  report.vaults = vaults.items.map((vault) => ({ id: vault.id, name: vault.name, items: vault.item_count, exists: vault.exists }));
  for (const id of ['default', 'imported-smoke', 'merged-smoke', 'restored-default']) {
    if (!report.vaults.some((vault) => vault.id === id && vault.exists)) throw new Error(`missing vault after smoke: ${id}`);
  }
  await shot(page, '10-smoke-complete');

  await browser.close();
  fs.writeFileSync(path.join(workspace, 'real-vault-smoke-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  fs.writeFileSync(path.join(workspace, 'real-vault-smoke-error.txt'), error.stack || String(error));
  console.error(error);
  process.exit(1);
}).finally(() => {
  if (backendProc) backendProc.kill();
  if (viteProc) viteProc.kill();
});
