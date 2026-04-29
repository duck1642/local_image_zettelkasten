export interface VaultItem {
    hash: string;
    extension: string;
    mime_type: string;
    original_filename: string;
    source_url: string;
    date_added: string;
    platform: string;
    artist: string;
    url: string;
    thumbnail_url: string;
    width: number | null;
    height: number | null;
}

export type VaultGroup = {
    id: string;
    items: VaultItem[];
};

export type SuggestionKind = 'none' | 'command' | 'artist' | 'platform' | 'topic' | 'wd_tag';

export type FacetSuggestion = {
    value: string;
    count?: number;
};

export type SearchFilters = {
    artists: string[];
    platforms: string[];
    topics: string[];
    wd_tags: string[];
    text_terms: string[];
    command?: string;
};

export type ActiveSegment = {
    kind: SuggestionKind;
    prefix: string;
    value: string;
    segmentStart: number;
    segmentEnd: number;
    valueStart: number;
};
