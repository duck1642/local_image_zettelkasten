export function updateSelection(
  selectedHashes: Set<string>,
  orderedHashes: string[],
  clickedHash: string,
  lastSelectedHash: string | null,
  event?: MouseEvent
) {
  const additive = Boolean(event?.ctrlKey || event?.metaKey);
  const range = Boolean(event?.shiftKey && lastSelectedHash);

  if (range) {
    const start = orderedHashes.indexOf(lastSelectedHash || '');
    const end = orderedHashes.indexOf(clickedHash);
    if (start >= 0 && end >= 0) {
      const [from, to] = start <= end ? [start, end] : [end, start];
      const next = new Set(selectedHashes);
      for (const hash of orderedHashes.slice(from, to + 1)) next.add(hash);
      return { selectedHashes: next, lastSelectedHash };
    }
    return { selectedHashes: new Set([clickedHash]), lastSelectedHash: clickedHash };
  }

  if (additive) {
    const next = new Set(selectedHashes);
    if (next.has(clickedHash)) next.delete(clickedHash);
    else next.add(clickedHash);
    return { selectedHashes: next, lastSelectedHash: clickedHash };
  }

  return { selectedHashes: new Set([clickedHash]), lastSelectedHash: clickedHash };
}
