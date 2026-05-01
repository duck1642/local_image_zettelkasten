import type { VaultGroup, VaultItem } from './types';

export const EXPERIMENTAL_MASONRY_OVERSCAN = 1500;
export const EXPERIMENTAL_MASONRY_DRIFT_THRESHOLD = 20;

export type ExperimentalMasonryRow = {
  group: VaultGroup;
  columnIndex: number;
  groupIndex: number;
  top: number;
  estimatedHeight: number;
  bottom: number;
};

export type ExperimentalMasonryColumn = {
  rows: ExperimentalMasonryRow[];
};

function activeItem(group: VaultGroup, activeIndex = 0): VaultItem | undefined {
  return group.items[Math.min(Math.max(activeIndex || 0, 0), Math.max(0, group.items.length - 1))];
}

export function estimateExperimentalGroupHeight(group: VaultGroup, columnWidth: number, activeIndex = 0) {
  const item = activeItem(group, activeIndex);
  const ratio = item?.width && item?.height ? item.height / item.width : 1;
  const mediaHeight = Math.max(100, columnWidth * ratio);
  return mediaHeight + 37;
}

export function buildExperimentalMasonryColumns(
  columns: VaultGroup[][],
  columnWidth: number,
  activeIndexes: Record<string, number>,
  gap = 12
): ExperimentalMasonryColumn[] {
  return columns.map((column, columnIndex) => {
    let top = 0;
    const rows = column.map((group, groupIndex) => {
      const estimatedHeight = estimateExperimentalGroupHeight(group, columnWidth, activeIndexes[group.id] || 0);
      const row = {
        group,
        columnIndex,
        groupIndex,
        top,
        estimatedHeight,
        bottom: top + estimatedHeight
      };
      top += estimatedHeight + gap;
      return row;
    });
    return { rows };
  });
}

export function rowIsVisible(row: ExperimentalMasonryRow, scrollTop: number, viewportHeight: number, overscan = EXPERIMENTAL_MASONRY_OVERSCAN) {
  return row.bottom > scrollTop - overscan && row.top < scrollTop + viewportHeight + overscan;
}
