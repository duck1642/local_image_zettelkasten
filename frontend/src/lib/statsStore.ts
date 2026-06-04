import { writable } from 'svelte/store';
import { apiFetch } from './api';
import { log as uiLog } from './logger';

export type QueueStats = {
  normal: number;
  force: number;
  failed: number;
};

export type ReviewStats = {
  count: number;
  pending: number;
  cleanup: number;
};

const initialQueueStats: QueueStats = { normal: 0, force: 0, failed: 0 };
const initialReviewStats: ReviewStats = { count: 0, pending: 0, cleanup: 0 };

export const queueStats = writable<QueueStats>(initialQueueStats);
export const reviewCount = writable(0);
export const reviewStats = writable<ReviewStats>(initialReviewStats);

export function setQueueStats(next: QueueStats) {
  queueStats.set({
    normal: Number(next?.normal) || 0,
    force: Number(next?.force) || 0,
    failed: Number(next?.failed) || 0
  });
}

export function clearSharedStats() {
  queueStats.set(initialQueueStats);
  reviewCount.set(0);
  reviewStats.set(initialReviewStats);
}

export async function refreshQueueStats() {
  try {
    const response = await apiFetch('/api/queue-stats');
    const data = await response.json();
    setQueueStats(data);
    return data as QueueStats;
  } catch (error) {
    uiLog('ERROR', 'Failed to refresh queue stats', { error: String(error) });
    throw error;
  }
}

export async function refreshReviewCount() {
  try {
    const response = await apiFetch('/api/review/count');
    const data = await response.json();
    const count = Number(data?.count) || 0;
    const stats = {
      count,
      pending: Number(data?.pending) || count,
      cleanup: Number(data?.cleanup) || 0
    };
    reviewCount.set(count);
    reviewStats.set(stats);
    return stats;
  } catch (error) {
    uiLog('ERROR', 'Failed to refresh review count', { error: String(error) });
    throw error;
  }
}

export async function refreshSharedStats() {
  await Promise.all([refreshQueueStats(), refreshReviewCount()]);
}

export function startSharedStatsPolling(queueIntervalMs = 1000, reviewIntervalMs = 5000) {
  refreshSharedStats().catch(() => undefined);
  const queueTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      refreshQueueStats().catch(() => undefined);
    }
  }, queueIntervalMs);
  const reviewTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      refreshReviewCount().catch(() => undefined);
    }
  }, reviewIntervalMs);
  const refreshOnFocus = () => refreshSharedStats().catch(() => undefined);
  window.addEventListener('focus', refreshOnFocus);
  document.addEventListener('visibilitychange', refreshOnFocus);
  return () => {
    window.clearInterval(queueTimer);
    window.clearInterval(reviewTimer);
    window.removeEventListener('focus', refreshOnFocus);
    document.removeEventListener('visibilitychange', refreshOnFocus);
  };
}
