export type TileMeasurement = {
  width: number;
  height: number;
  ratio: number;
};

export type MeasurementStore = Record<string, TileMeasurement>;

export function measuredHeightFor(store: MeasurementStore, groupId: string, width: number) {
  const measurement = store[groupId];
  if (!measurement || measurement.ratio <= 0) return null;
  return Math.max(1, width * measurement.ratio);
}

export function withMeasurement(store: MeasurementStore, groupId: string, width: number, height: number) {
  if (width <= 0 || height <= 0) return store;
  const next = {
    width,
    height,
    ratio: height / width
  };
  const current = store[groupId];
  if (
    current &&
    Math.abs(current.width - next.width) < 1 &&
    Math.abs(current.height - next.height) < 1 &&
    Math.abs(current.ratio - next.ratio) < 0.002
  ) {
    return store;
  }
  return { ...store, [groupId]: next };
}
