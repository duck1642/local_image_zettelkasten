import { DEFAULT_TILE_MIN_WIDTH, columnCountFor, normalizeTileMinWidth } from '../../layout';
import type { VaultGroup, VaultItem } from '../../types';
import { measuredHeightFor, type MeasurementStore } from './measurementStore';

export const MASONRY_GAP = 12;
export const MASONRY_OVERSCAN = 1200;
export const MASONRY_DRIFT_THRESHOLD = 20;
const ESTIMATED_CHROME_HEIGHT = 34; // 16px padding + 14px text + 4px border
const CSS_BORDER_WIDTH = 4; // 2px solid border on left/right
const MIN_MEDIA_HEIGHT = 100;

export type MasonryPosition = {
  group: VaultGroup;
  columnIndex: number;
  left: number;
  top: number;
  width: number;
  height: number;
  bottom: number;
  estimated: boolean;
  columnHeightsBefore: number[];
};

export type MasonryLayout = {
  positions: MasonryPosition[];
  columnCount: number;
  columnWidth: number;
  totalHeight: number;
  columnHeights: number[];
};

function activeItem(group: VaultGroup, activeIndex: number): VaultItem | undefined {
  const index = Math.min(Math.max(activeIndex || 0, 0), Math.max(0, group.items.length - 1));
  return group.items[index] || group.items[0];
}

export function estimateMasonryGroupHeight(group: VaultGroup, columnWidth: number, activeIndex = 0, store: MeasurementStore = {}) {
  const measured = measuredHeightFor(store, group.id, columnWidth);
  if (measured !== null) return { height: measured, estimated: false };
  const item = activeItem(group, activeIndex);
  const ratio = item?.width && item?.height ? item.height / item.width : 1;
  const innerWidth = Math.max(1, columnWidth - CSS_BORDER_WIDTH);
  const mediaHeight = Math.max(MIN_MEDIA_HEIGHT, innerWidth * ratio);
  return { height: mediaHeight + ESTIMATED_CHROME_HEIGHT, estimated: true };
}

let lastCacheKey = '';
let lastCache: MasonryLayout | null = null;
let lastPositions: MasonryPosition[] = [];
let lastActiveIndexes: Record<string, number> = {};
let lastStore: MeasurementStore = {};

export function computeMasonryLayout(
  groups: VaultGroup[],
  width: number,
  minWidth = DEFAULT_TILE_MIN_WIDTH,
  activeIndexes: Record<string, number> = {},
  store: MeasurementStore = {},
  gap = MASONRY_GAP
): MasonryLayout {
  const normalizedMinWidth = normalizeTileMinWidth(minWidth);
  const safeWidth = Math.max(1, width);
  const columnCount = columnCountFor(safeWidth, normalizedMinWidth);
  const columnWidth = Math.max(1, (safeWidth - gap * (columnCount - 1)) / columnCount);
  
  const cacheKey = `${safeWidth}-${normalizedMinWidth}-${gap}-${columnCount}-${groups.length}`;
  let startIndex = 0;
  let columnHeights = Array.from({ length: columnCount }, () => 0);
  const positions: MasonryPosition[] = [];

  if (lastCacheKey === cacheKey && lastCache && lastPositions.length > 0 && groups.length >= lastPositions.length && groups[0].id === lastPositions[0].group.id) {
     for (let i = 0; i < lastPositions.length; i++) {
        const group = groups[i];
        const activeIdx = activeIndexes[group.id] || 0;
        const prevActive = lastActiveIndexes[group.id] || 0;
        
        const { height, estimated } = estimateMasonryGroupHeight(group, columnWidth, activeIdx, store);
        const prevPos = lastPositions[i];
        
        if (activeIdx !== prevActive || height !== prevPos.height || group.id !== prevPos.group.id) {
           startIndex = i;
           columnHeights = [...prevPos.columnHeightsBefore];
           break;
        }
        positions.push(prevPos);
        startIndex = i + 1;
     }
     if (startIndex === groups.length && groups.length === lastPositions.length) {
         lastActiveIndexes = activeIndexes;
         lastStore = store;
         return lastCache;
     }
     if (startIndex === lastPositions.length) {
        columnHeights = [...lastPositions[lastPositions.length - 1].columnHeightsBefore];
        const lastPos = lastPositions[lastPositions.length - 1];
        columnHeights[lastPos.columnIndex] = lastPos.bottom + gap;
     }
  }

  for (let i = startIndex; i < groups.length; i++) {
    const group = groups[i];
    let columnIndex = 0;
    for (let index = 1; index < columnHeights.length; index += 1) {
      if (columnHeights[index] < columnHeights[columnIndex]) columnIndex = index;
    }
    const top = columnHeights[columnIndex];
    const { height, estimated } = estimateMasonryGroupHeight(group, columnWidth, activeIndexes[group.id] || 0, store);
    const left = columnIndex * (columnWidth + gap);
    const bottom = top + height;
    positions.push({ 
        group, columnIndex, left, top, width: columnWidth, height, bottom, estimated, 
        columnHeightsBefore: [...columnHeights] 
    });
    columnHeights[columnIndex] = bottom + gap;
  }

  const totalHeight = Math.max(0, ...columnHeights.map((value) => Math.max(0, value - gap)));
  const layout = {
    positions,
    columnCount,
    columnWidth,
    totalHeight,
    columnHeights: columnHeights.map((value) => Math.max(0, value - gap))
  };

  lastCacheKey = cacheKey;
  lastCache = layout;
  lastPositions = positions;
  lastActiveIndexes = activeIndexes;
  lastStore = store;

  return layout;
}

export function visibleMasonryPositions(
  positions: MasonryPosition[],
  scrollTop: number,
  viewportHeight: number,
  overscan = MASONRY_OVERSCAN
) {
  const min = scrollTop - overscan;
  const max = scrollTop + viewportHeight + overscan;
  const visible: MasonryPosition[] = [];
  for (const position of positions) {
    if (position.bottom >= min && position.top <= max) visible.push(position);
  }
  return visible;
}

export function visualOrderFromMasonryPositions(positions: MasonryPosition[]) {
  return [...positions]
    .sort((left, right) => left.top - right.top || left.left - right.left)
    .flatMap((position) => position.group.items.map((item) => item.hash));
}
