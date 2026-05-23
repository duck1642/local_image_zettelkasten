import { apiFetch } from '../api';
import type {
  ArtistDetail,
  ArtistDraft,
  ArtistLinkDraft,
  ArtistListItem,
  ArtistMergePreview,
  FacetItem,
  FacetKind,
  PlatformListItem,
  StatsScopeMode
} from './types';

async function jsonOrThrow(response: Response, fallback: string) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.detail || fallback || `HTTP ${response.status}`);
  return payload;
}

export async function fetchPlatformOptions() {
  const response = await apiFetch('/api/platforms?limit=200');
  const data = await jsonOrThrow(response, `Platform request failed: ${response.status}`);
  return Array.isArray(data.items) ? data.items as PlatformListItem[] : [];
}

export async function fetchArtistDetail(id: number) {
  const response = await apiFetch(`/api/artists/${id}`);
  return await jsonOrThrow(response, `Artist detail failed: ${response.status}`) as ArtistDetail;
}

export async function fetchArtists(q: string, scope: StatsScopeMode, limit = 200) {
  const params = new URLSearchParams({ q: q.trim(), limit: String(limit), scope });
  const response = await apiFetch(`/api/artists?${params.toString()}`);
  const data = await jsonOrThrow(response, `Artist request failed: ${response.status}`);
  return Array.isArray(data.items) ? data.items as ArtistListItem[] : [];
}

export async function fetchArtistPlaceholders(q: string) {
  const params = new URLSearchParams({ kind: 'artist', q: q.trim(), limit: '200' });
  const response = await apiFetch(`/api/facets?${params.toString()}`);
  const data = await jsonOrThrow(response, `Artist placeholder request failed: ${response.status}`);
  return Array.isArray(data.items) ? data.items as FacetItem[] : [];
}

export async function fetchPlatformFacets(q: string, scope: StatsScopeMode) {
  const params = new URLSearchParams({ q: q.trim(), limit: '200', scope });
  const response = await apiFetch(`/api/platforms?${params.toString()}`);
  const data = await jsonOrThrow(response, `Platform request failed: ${response.status}`);
  return (Array.isArray(data.items) ? data.items as PlatformListItem[] : []).map((platform) => ({
    value: platform.display_name,
    count: platform.item_count
  }));
}

export async function fetchFacets(kind: FacetKind, q: string, scope: StatsScopeMode) {
  const params = new URLSearchParams({
    kind,
    q: q.trim(),
    limit: '200',
    scope: kind === 'topic' || kind === 'wd_tag' ? scope : 'used'
  });
  const response = await apiFetch(`/api/facets?${params.toString()}`);
  const data = await jsonOrThrow(response, `Facet request failed: ${response.status}`);
  return Array.isArray(data.items) ? data.items as FacetItem[] : [];
}

export async function fetchMergeCandidates(q: string, selectedArtistId: number) {
  const params = new URLSearchParams({ q: q.trim(), limit: '100' });
  const response = await apiFetch(`/api/artists?${params.toString()}`);
  const data = await jsonOrThrow(response, `Artist request failed: ${response.status}`);
  return (Array.isArray(data.items) ? data.items as ArtistListItem[] : []).filter((artist) => artist.id !== selectedArtistId);
}

export async function previewArtistMerge(artistId: number, sourceArtistIds: number[]) {
  const response = await apiFetch(`/api/artists/${artistId}/merge-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_artist_ids: sourceArtistIds })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`) as ArtistMergePreview;
}

export async function mergeArtists(artistId: number, sourceArtistIds: number[]) {
  const response = await apiFetch(`/api/artists/${artistId}/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_artist_ids: sourceArtistIds })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`) as ArtistMergePreview;
}

export async function saveArtistDetail(artistId: number, draft: ArtistDraft) {
  const response = await apiFetch(`/api/artists/${artistId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft)
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`) as ArtistDetail;
}

export async function addArtistAlias(artistId: number, alias: string) {
  const response = await apiFetch(`/api/artists/${artistId}/aliases`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alias: alias.trim() })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function deleteArtistAlias(artistId: number, aliasId: number) {
  const response = await apiFetch(`/api/artists/${artistId}/aliases/${aliasId}`, { method: 'DELETE' });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function addArtistLink(artistId: number, link: ArtistLinkDraft) {
  const response = await apiFetch(`/api/artists/${artistId}/links`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      platform: link.platform.trim(),
      url: link.url.trim(),
      handle: link.handle.trim()
    })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function deleteArtistLink(artistId: number, linkId: number) {
  const response = await apiFetch(`/api/artists/${artistId}/links/${linkId}`, { method: 'DELETE' });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function renameTopic(oldLabel: string, newLabel: string) {
  const response = await apiFetch('/api/topics/rename', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_label: oldLabel, new_label: newLabel.trim() })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function createTopic(label: string) {
  const response = await apiFetch('/api/topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: label.trim() })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function deleteTopic(label: string) {
  const response = await apiFetch('/api/topics/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function mergeTopic(sourceLabel: string, targetLabel: string) {
  const response = await apiFetch('/api/topics/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_label: sourceLabel, target_label: targetLabel.trim() })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function renameWdTag(oldTag: string, newTag: string, tagType = '') {
  const response = await apiFetch('/api/wd-tags/rename', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_tag: oldTag, new_tag: newTag.trim(), tag_type: tagType || null })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}

export async function deleteWdTag(tag: string, tagType = '') {
  const response = await apiFetch('/api/wd-tags/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tag, tag_type: tagType || null })
  });
  return await jsonOrThrow(response, `HTTP ${response.status}`);
}
