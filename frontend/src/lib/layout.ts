import type { VaultGroup, VaultItem } from './types';

export type VaultLayoutMode = 'masonry' | 'grid';
export const DEFAULT_TILE_MIN_WIDTH = 190;
export const TILE_MIN_WIDTH_FLOOR = 140;
export const TILE_MIN_WIDTH_CEILING = 360;

export function normalizeLayoutMode(config: any): VaultLayoutMode {
  const mode = config?.ui?.vault_layout_mode;
  if (mode === 'masonry' || mode === 'grid') return mode;
  if (mode === 'masonry-js') return 'masonry';
  if (mode === 'grid-js') return 'grid';
  const legacy = config?.ui?.vault_layout;
  return legacy === 'grid' ? 'grid' : 'masonry';
}

export function normalizeTileMinWidth(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return DEFAULT_TILE_MIN_WIDTH;
  return Math.max(TILE_MIN_WIDTH_FLOOR, Math.min(TILE_MIN_WIDTH_CEILING, Math.round(numeric)));
}

export function columnCountFor(width: number, minWidth = DEFAULT_TILE_MIN_WIDTH) {
  return Math.max(1, Math.floor(Math.max(0, width) / normalizeTileMinWidth(minWidth)));
}

function primaryItem(group: VaultGroup): VaultItem | undefined {
  return group.items[0];
}

export function estimateGroupHeight(group: VaultGroup, columnWidth: number) {
  const item = primaryItem(group);
  const ratio = item?.width && item?.height ? item.height / item.width : 1;
  const mediaHeight = Math.max(100, columnWidth * ratio);
  return mediaHeight + 37;
}

export function buildMasonryColumns(groups: VaultGroup[], width: number, minWidth = DEFAULT_TILE_MIN_WIDTH, gap = 12) {
  const normalizedMinWidth = normalizeTileMinWidth(minWidth);
  const safeWidth = Math.max(1, width);
  const count = columnCountFor(safeWidth, normalizedMinWidth);
  const columnWidth = Math.max(1, (safeWidth - gap * (count - 1)) / count);
  const columns = Array.from({ length: count }, () => ({ height: 0, groups: [] as VaultGroup[] }));

  for (const group of groups) {
    const target = columns.reduce((shortest, column) => (column.height < shortest.height ? column : shortest), columns[0]);
    target.groups.push(group);
    target.height += estimateGroupHeight(group, columnWidth) + gap;
  }

  return columns.map((column) => column.groups);
}

export function visualOrderForRenderedGroups(columns: VaultGroup[][]) {
  return columns.flatMap((column) => column.flatMap((group) => group.items.map((item) => item.hash)));
}
