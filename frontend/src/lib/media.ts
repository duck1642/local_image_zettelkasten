import type { VaultItem } from './types';

export function mediaMime(item: Pick<VaultItem, 'mime_type'> | null | undefined) {
  return String(item?.mime_type || '');
}

export function isImageMedia(item: Pick<VaultItem, 'mime_type'> | null | undefined) {
  return mediaMime(item).startsWith('image/');
}

export function isVideoMedia(item: Pick<VaultItem, 'mime_type'> | null | undefined) {
  return mediaMime(item).startsWith('video/');
}
