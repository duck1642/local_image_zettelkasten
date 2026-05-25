export type FacetKind = 'wd_tag' | 'artist' | 'platform' | 'topic';
export type StatsSortMode = 'popularity' | 'alphabetical';
export type StatsScopeMode = 'used' | 'all';
export type MetadataActionKind = 'rename' | 'delete' | 'merge';

export type FacetItem = { value: string; count: number; tag_type?: 'rating' | 'character' | 'general' | string };
export type FilterVaultPayload = { topics: string[]; wd_tags: string[] };
export type ArtistListItem = { id: number; name: string; kind: string; item_count: number; link_count: number; alias_count: number };
export type ArtistAlias = { id: number; alias: string; alias_norm: string };
export type ArtistLink = { id: number; platform: string; url: string; handle: string; is_primary: boolean };
export type PlatformListItem = { id: number; key_norm: string; display_name: string; kind: string; item_count: number; alias_count: number };

export type ArtistDetail = {
  id: number;
  name: string;
  name_norm: string;
  kind: string;
  notes: string;
  item_count: number;
  aliases: ArtistAlias[];
  links: ArtistLink[];
};

export type ArtistDraft = { name: string; kind: string; notes: string };
export type ArtistLinkDraft = { platform: string; url: string; handle: string };

export type ArtistMergePreview = {
  target: { id: number; name: string };
  sources: Array<{ id: number; name: string }>;
  affected_items: number;
  aliases: {
    add: Array<{ value: string }>;
    move: Array<{ value: string }>;
    duplicates: Array<{ value: string; reason: string }>;
    conflicts: Array<{ value: string; reason: string }>;
  };
  links: {
    move: Array<{ url: string }>;
    duplicates: Array<{ url: string }>;
  };
  notes_appended: number;
  source_artists_deleted: number;
  target_detail?: ArtistDetail;
  merged?: boolean;
};

export const statsKinds: { label: string; value: FacetKind }[] = [
  { label: 'WD Tags', value: 'wd_tag' },
  { label: 'Topics', value: 'topic' },
  { label: 'Artists', value: 'artist' },
  { label: 'Platforms', value: 'platform' }
];

export const letterFilters = ['all', '#', ...'abcdefghijklmnopqrstuvwxyz'.split('')];
