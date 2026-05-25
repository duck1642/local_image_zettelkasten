export interface ReviewMatch {
  hash: string;
  url: string;
  artist: string;
  mime_type?: string;
  extension?: string;
  width?: number;
  height?: number;
  size_bytes?: number;
  codec?: string;
  duration?: number;
  frames?: number;
  wd_tags?: string[];
  audio_present?: boolean;
}

export interface ReviewItem {
  filename: string;
  display_name?: string;
  url: string;
  mime_type?: string;
  extension?: string;
  metadata: any;
  state?: string;
  section?: 'pending' | 'cleanup';
  last_action?: string;
  last_cleanup_error?: string;
  validation_warning?: string;
  best_match: ReviewMatch | null;
  matches?: ReviewMatch[];
}

export type MediaInfo = {
  url?: string;
  filename?: string;
  mime_type?: string;
  extension?: string;
} | null | undefined;

export function extFromUrl(url: string) {
  const clean = (url || '').split('?')[0].split('#')[0];
  const dot = clean.lastIndexOf('.');
  if (dot < 0) return '';
  return clean.slice(dot).toLowerCase();
}

export function resolvedReviewMatches(item: ReviewItem | null | undefined): ReviewMatch[] {
  if (!item) return [];
  return item.matches && item.matches.length > 0
    ? item.matches
    : (item.best_match ? [item.best_match] : []);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return 'unknown size';
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDuration(sec: number | null | undefined): string {
  if (sec == null || sec <= 0) return '';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export function reviewComparisonData(item: ReviewItem | null | undefined, activeMatchIndex: number) {
  const resolvedMatches = resolvedReviewMatches(item);
  const activeMatch = resolvedMatches[activeMatchIndex] || null;
  const metadata = item?.metadata || {};

  const stagedWidth = metadata?.width || metadata?.metadata?.width || 0;
  const stagedHeight = metadata?.height || metadata?.metadata?.height || 0;
  const stagedSize = metadata?.size_bytes || 0;
  const stagedCodec = metadata?.codec || '';
  const stagedDuration = metadata?.duration || 0;
  const stagedFrames = metadata?.frames || 0;
  const stagedWdTags = metadata?.wd_tags || metadata?.metadata?.wd_tags || [];

  const vaultWidth = activeMatch?.width || 0;
  const vaultHeight = activeMatch?.height || 0;
  const vaultSize = activeMatch?.size_bytes || 0;
  const vaultCodec = activeMatch?.codec || '';
  const vaultDuration = activeMatch?.duration || 0;
  const vaultFrames = activeMatch?.frames || 0;
  const vaultWdTags = activeMatch?.wd_tags || [];

  const stagedRes = stagedWidth * stagedHeight;
  const vaultRes = vaultWidth * vaultHeight;

  return {
    resolvedMatches,
    activeMatch,
    stagedWidth,
    stagedHeight,
    stagedSize,
    stagedCodec,
    stagedDuration,
    stagedFrames,
    stagedWdTags,
    vaultWidth,
    vaultHeight,
    vaultSize,
    vaultCodec,
    vaultDuration,
    vaultFrames,
    vaultWdTags,
    resClassStaged: stagedRes > 0 && vaultRes > 0
      ? (stagedRes > vaultRes ? 'better' : (stagedRes < vaultRes ? 'worse' : ''))
      : '',
    resClassVault: stagedRes > 0 && vaultRes > 0
      ? (vaultRes > stagedRes ? 'better' : (vaultRes < stagedRes ? 'worse' : ''))
      : '',
    sizeClassStaged: stagedSize > 0 && vaultSize > 0
      ? (stagedSize > vaultSize ? 'better' : (stagedSize < vaultSize ? 'worse' : ''))
      : '',
    sizeClassVault: stagedSize > 0 && vaultSize > 0
      ? (vaultSize > stagedSize ? 'better' : (vaultSize < stagedSize ? 'worse' : ''))
      : ''
  };
}
