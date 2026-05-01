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
