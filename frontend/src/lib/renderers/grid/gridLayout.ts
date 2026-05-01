import { DEFAULT_TILE_MIN_WIDTH, columnCountFor, normalizeTileMinWidth } from '../../layout';
import type { VaultGroup } from '../../types';

export const GRID_GAP = 15;
export const GRID_OVERSCAN = 1200;
const GRID_CHROME_HEIGHT = 41;

export type GridPosition = {
  group: VaultGroup;
  rowIndex: number;
  columnIndex: number;
  left: number;
  top: number;
  width: number;
  height: number;
  bottom: number;
};

export type GridLayout = {
  positions: GridPosition[];
  columnCount: number;
  columnWidth: number;
  rowHeight: number;
  totalHeight: number;
};

export function computeGridLayout(
  groups: VaultGroup[],
  width: number,
  minWidth = DEFAULT_TILE_MIN_WIDTH,
  gap = GRID_GAP
): GridLayout {
  const normalizedMinWidth = normalizeTileMinWidth(minWidth);
  const safeWidth = Math.max(1, width);
  const columnCount = columnCountFor(safeWidth, normalizedMinWidth);
  const columnWidth = Math.max(1, (safeWidth - gap * (columnCount - 1)) / columnCount);
  const rowHeight = Math.max(1, columnWidth + GRID_CHROME_HEIGHT);
  const positions = groups.map((group, index) => {
    const rowIndex = Math.floor(index / columnCount);
    const columnIndex = index % columnCount;
    const left = columnIndex * (columnWidth + gap);
    const top = rowIndex * (rowHeight + gap);
    const bottom = top + rowHeight;
    return { group, rowIndex, columnIndex, left, top, width: columnWidth, height: rowHeight, bottom };
  });
  const rowCount = Math.ceil(groups.length / columnCount);
  const totalHeight = rowCount > 0 ? rowCount * rowHeight + Math.max(0, rowCount - 1) * gap : 0;
  return { positions, columnCount, columnWidth, rowHeight, totalHeight };
}

export function visibleGridPositions(
  positions: GridPosition[],
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  columnCount: number,
  overscan = GRID_OVERSCAN,
  gap = GRID_GAP
) {
  if (positions.length === 0 || rowHeight <= 0 || columnCount <= 0) return [];
  const rowPitch = rowHeight + gap;
  const startRow = Math.max(0, Math.floor((scrollTop - overscan) / rowPitch));
  const endRow = Math.max(startRow, Math.floor((scrollTop + viewportHeight + overscan) / rowPitch));
  const startIndex = startRow * columnCount;
  const endIndex = Math.min(positions.length, (endRow + 1) * columnCount);
  return positions.slice(startIndex, endIndex);
}

export function visualOrderFromGridPositions(positions: GridPosition[]) {
  return [...positions]
    .sort((left, right) => left.rowIndex - right.rowIndex || left.columnIndex - right.columnIndex)
    .flatMap((position) => position.group.items.map((item) => item.hash));
}
