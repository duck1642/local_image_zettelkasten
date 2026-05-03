import type { ActiveSegment, SearchFilters } from './types';

export function emptyFilters(): SearchFilters {
  return { artists: [], platforms: [], topics: [], wd_tags: [], text_terms: [] };
}

export function hasActiveFilters(filters: SearchFilters) {
  return Boolean(
    filters.command ||
    filters.artists.length ||
    filters.platforms.length ||
    filters.topics.length ||
    filters.wd_tags.length ||
    filters.text_terms.length
  );
}

export function parseSearchQuery(query: string): SearchFilters {
  const filters = emptyFilters();
  const segments = query.split(';').map((segment) => segment.trim()).filter(Boolean);

  for (const segment of segments) {
    if (segment.startsWith('a:')) {
      const value = segment.slice(2).trim();
      if (value) filters.artists.push(value);
    } else if (segment.startsWith('@')) {
      const value = segment.slice(1).trim();
      if (value) filters.platforms.push(value);
    } else if (segment.startsWith('#')) {
      const value = segment.slice(1).trim();
      if (value) filters.topics.push(value);
    } else if (segment.startsWith('*')) {
      const value = segment.slice(1).trim();
      if (value) filters.wd_tags.push(value);
    } else if (segment.startsWith('>')) {
      const value = segment.slice(1).trim();
      if (value) filters.command = value;
    } else {
      filters.text_terms.push(...segment.split(/\s+/).filter(Boolean));
    }
  }

  return filters;
}

export function buildItemQueryParams(filters: SearchFilters, sort: string, mediaType: string, limit: string, cursor?: string | null) {
  const params = new URLSearchParams({ sort, media_type: mediaType, limit });
  if (cursor) params.set('cursor', cursor);
  filters.artists.forEach((value) => params.append('artist', value));
  filters.platforms.forEach((value) => params.append('platform', value));
  filters.topics.forEach((value) => params.append('topic', value));
  filters.wd_tags.forEach((value) => params.append('wd_tag', value));
  filters.text_terms.forEach((value) => params.append('text', value));
  return params;
}

export function getActiveSegment(query: string, cursor: number): ActiveSegment {
  const segmentStart = query.lastIndexOf(';', Math.max(0, cursor - 1)) + 1;
  const nextSeparator = query.indexOf(';', cursor);
  const segmentEnd = nextSeparator === -1 ? query.length : nextSeparator;
  const rawSegment = query.slice(segmentStart, segmentEnd);
  const leadingLength = rawSegment.length - rawSegment.trimStart().length;
  const contentStart = segmentStart + leadingLength;
  const content = query.slice(contentStart, segmentEnd);

  if (content.startsWith('a:')) return { kind: 'artist', prefix: 'a:', value: query.slice(contentStart + 2, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 2 };
  if (content.startsWith('@')) return { kind: 'platform', prefix: '@', value: query.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
  if (content.startsWith('#')) return { kind: 'topic', prefix: '#', value: query.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
  if (content.startsWith('*')) return { kind: 'wd_tag', prefix: '*', value: query.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
  if (content.startsWith('>')) return { kind: 'command', prefix: '>', value: query.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
  return { kind: 'none', prefix: '', value: '', segmentStart: contentStart, segmentEnd, valueStart: contentStart };
}
