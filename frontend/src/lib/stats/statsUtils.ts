import type { ArtistListItem, FacetItem, FacetKind, StatsSortMode } from './types';

const placeholderArtistNorms = new Set(['', 'unknown', 'local', 'none', 'n/a', 'na', 'null']);

export function isPlaceholderArtist(value: string) {
  return placeholderArtistNorms.has(String(value || '').trim().toLowerCase());
}

export function firstBucket(value: string) {
  const first = String(value || '').trim().charAt(0).toLowerCase();
  return first >= 'a' && first <= 'z' ? first : '#';
}

export function matchesLetter(value: string, activeLetter: string) {
  return activeLetter === 'all' || firstBucket(value) === activeLetter;
}

export function filterFacetsByLetter(values: FacetItem[], enabled: boolean, activeLetter: string) {
  if (!enabled || activeLetter === 'all') return values;
  return values.filter((item) => matchesLetter(item.value, activeLetter));
}

export function filterArtistsByLetter(values: ArtistListItem[], enabled: boolean, activeLetter: string) {
  if (!enabled || activeLetter === 'all') return values;
  return values.filter((artist) => matchesLetter(artist.name, activeLetter));
}

export function sortFacetItems(values: FacetItem[], sortMode: StatsSortMode) {
  const sorted = [...values];
  if (sortMode === 'alphabetical') {
    sorted.sort((a, b) => a.value.localeCompare(b.value, undefined, { sensitivity: 'base' }));
    return sorted;
  }
  sorted.sort((a, b) => b.count - a.count || a.value.localeCompare(b.value, undefined, { sensitivity: 'base' }));
  return sorted;
}

export function sortArtistItems(values: ArtistListItem[], sortMode: StatsSortMode) {
  const sorted = [...values];
  if (sortMode === 'alphabetical') {
    sorted.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
    return sorted;
  }
  sorted.sort((a, b) => b.item_count - a.item_count || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  return sorted;
}

export function isSelectableFacet(kind: FacetKind) {
  return kind === 'topic' || kind === 'wd_tag';
}

export function normalizeArtistListWidth(width: number) {
  return Math.max(220, Math.min(520, Math.round(width)));
}
