import { DEFAULT_TILE_MIN_WIDTH, columnCountFor, normalizeTileMinWidth } from '../../layout';
import type { VaultGroup } from '../../types';

export const GRID_EXP_GAP = 15;
export const GRID_EXP_OVERSCAN = 1200;
const GRID_EXP_CHROME_HEIGHT = 41;

export type GridExpPosition = {
  group: VaultGroup;
  rowIndex: number;
  columnIndex: number;
  left: number;
  top: number;
  width: number;
  height: number;
  bottom: number;
};

export type GridExpLayout = {
  positions: GridExpPosition[];
  columnCount: number;
  columnWidth: number;
  rowHeight: number;
  totalHeight: number;
};

export function computeGridExpLayout(
  groups: VaultGroup[],
  width: number,
  minWidth = DEFAULT_TILE_MIN_WIDTH,
  gap = GRID_EXP_GAP
): GridExpLayout {
  const normalizedMinWidth = normalizeTileMinWidth(minWidth);
  const safeWidth = Math.max(1, width);
  const columnCount = columnCountFor(safeWidth, normalizedMinWidth);
  const columnWidth = Math.max(1, (safeWidth - gap * (columnCount - 1)) / columnCount);
  const rowHeight = Math.max(1, columnWidth + GRID_EXP_CHROME_HEIGHT);
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

export function visibleGridExpPositions(
  positions: GridExpPosition[],
  scrollTop: number,
  viewportHeight: number,
  overscan = GRID_EXP_OVERSCAN
) {
  const min = scrollTop - overscan;
  const max = scrollTop + viewportHeight + overscan;
  return positions.filter((position) => position.bottom >= min && position.top <= max);
}

export function visualOrderFromGridExpPositions(positions: GridExpPosition[]) {
  return [...positions]
    .sort((left, right) => left.rowIndex - right.rowIndex || left.columnIndex - right.columnIndex)
    .flatMap((position) => position.group.items.map((item) => item.hash));
}
