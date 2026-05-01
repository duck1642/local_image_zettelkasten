import { DEFAULT_TILE_MIN_WIDTH, columnCountFor, normalizeTileMinWidth } from '../../layout';
import type { VaultGroup, VaultItem } from '../../types';
import { measuredHeightFor, type MeasurementStore } from './measurementStore';

export const MEASURED_MASONRY_GAP = 12;
export const MEASURED_MASONRY_OVERSCAN = 1200;
export const MEASURED_MASONRY_DRIFT_THRESHOLD = 20;
const ESTIMATED_CHROME_HEIGHT = 41;
const MIN_MEDIA_HEIGHT = 100;

export type MeasuredMasonryPosition = {
  group: VaultGroup;
  columnIndex: number;
  left: number;
  top: number;
  width: number;
  height: number;
  bottom: number;
  estimated: boolean;
};

export type MeasuredMasonryLayout = {
  positions: MeasuredMasonryPosition[];
  columnCount: number;
  columnWidth: number;
  totalHeight: number;
  columnHeights: number[];
};

function activeItem(group: VaultGroup, activeIndex: number): VaultItem | undefined {
  const index = Math.min(Math.max(activeIndex || 0, 0), Math.max(0, group.items.length - 1));
  return group.items[index] || group.items[0];
}

export function estimateMeasuredGroupHeight(group: VaultGroup, columnWidth: number, activeIndex = 0, store: MeasurementStore = {}) {
  const measured = measuredHeightFor(store, group.id, columnWidth);
  if (measured !== null) return { height: measured, estimated: false };
  const item = activeItem(group, activeIndex);
  const ratio = item?.width && item?.height ? item.height / item.width : 1;
  const mediaHeight = Math.max(MIN_MEDIA_HEIGHT, columnWidth * ratio);
  return { height: mediaHeight + ESTIMATED_CHROME_HEIGHT, estimated: true };
}

export function computeMeasuredMasonryLayout(
  groups: VaultGroup[],
  width: number,
  minWidth = DEFAULT_TILE_MIN_WIDTH,
  activeIndexes: Record<string, number> = {},
  store: MeasurementStore = {},
  gap = MEASURED_MASONRY_GAP
): MeasuredMasonryLayout {
  const normalizedMinWidth = normalizeTileMinWidth(minWidth);
  const columnCount = columnCountFor(width, normalizedMinWidth);
  const columnWidth = Math.max(normalizedMinWidth, (Math.max(0, width) - gap * (columnCount - 1)) / columnCount);
  const columnHeights = Array.from({ length: columnCount }, () => 0);
  const positions: MeasuredMasonryPosition[] = [];

  for (const group of groups) {
    let columnIndex = 0;
    for (let index = 1; index < columnHeights.length; index += 1) {
      if (columnHeights[index] < columnHeights[columnIndex]) columnIndex = index;
    }
    const top = columnHeights[columnIndex];
    const { height, estimated } = estimateMeasuredGroupHeight(group, columnWidth, activeIndexes[group.id] || 0, store);
    const left = columnIndex * (columnWidth + gap);
    const bottom = top + height;
    positions.push({ group, columnIndex, left, top, width: columnWidth, height, bottom, estimated });
    columnHeights[columnIndex] = bottom + gap;
  }

  const totalHeight = Math.max(0, ...columnHeights.map((value) => Math.max(0, value - gap)));
  return {
    positions,
    columnCount,
    columnWidth,
    totalHeight,
    columnHeights: columnHeights.map((value) => Math.max(0, value - gap))
  };
}

export function visibleMeasuredPositions(
  positions: MeasuredMasonryPosition[],
  scrollTop: number,
  viewportHeight: number,
  overscan = MEASURED_MASONRY_OVERSCAN
) {
  const min = scrollTop - overscan;
  const max = scrollTop + viewportHeight + overscan;
  return positions.filter((position) => position.bottom >= min && position.top <= max);
}

export function visualOrderFromMeasuredPositions(positions: MeasuredMasonryPosition[]) {
  return [...positions]
    .sort((left, right) => left.top - right.top || left.left - right.left)
    .flatMap((position) => position.group.items.map((item) => item.hash));
}
