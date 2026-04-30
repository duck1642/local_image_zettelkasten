import { writable } from 'svelte/store';
import { apiFetch } from './api';
import { log as uiLog } from './logger';

export type QueueStats = {
  normal: number;
  force: number;
  failed: number;
};

const initialQueueStats: QueueStats = { normal: 0, force: 0, failed: 0 };

export const queueStats = writable<QueueStats>(initialQueueStats);
export const reviewCount = writable(0);

export function setQueueStats(next: QueueStats) {
  queueStats.set({
    normal: Number(next?.normal || 0),
    force: Number(next?.force || 0),
    failed: Number(next?.failed || 0)
  });
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
    const count = Number(data?.count || 0);
    reviewCount.set(count);
    return count;
  } catch (error) {
    uiLog('ERROR', 'Failed to refresh review count', { error: String(error) });
    throw error;
  }
}

export async function refreshSharedStats() {
  await Promise.all([refreshQueueStats(), refreshReviewCount()]);
}

export function startSharedStatsPolling(intervalMs = 5000) {
  refreshSharedStats().catch(() => undefined);
  const timer = window.setInterval(() => {
    refreshSharedStats().catch(() => undefined);
  }, intervalMs);
  return () => window.clearInterval(timer);
}
