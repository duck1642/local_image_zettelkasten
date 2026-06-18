import { writable } from 'svelte/store';

export type ToastType = 'success' | 'warning' | 'error' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message: string;
  duration?: number;
}

export interface ToastHistoryEntry extends Toast {
  createdAt: number;
  read: boolean;
}

const activeToasts = writable<Toast[]>([]);
const history = writable<ToastHistoryEntry[]>([]);

export const toastStore = {
  subscribe: activeToasts.subscribe,
  add(toast: Omit<Toast, 'id'>) {
    const id = Math.random().toString(36).slice(2, 9);
    const duration = toast.duration ?? 4000;
    activeToasts.update(toasts => {
      const next = [...toasts, { ...toast, id, duration }];
      if (next.length > 3) {
        return next.slice(next.length - 3);
      }
      return next;
    });
    history.update(entries => [
      { ...toast, id, duration, createdAt: Date.now(), read: false },
      ...entries
    ].slice(0, 50));
    
    if (duration > 0) {
      setTimeout(() => {
        this.dismiss(id);
      }, duration);
    }
    return id;
  },
  dismiss(id: string) {
    activeToasts.update(toasts => toasts.filter(t => t.id !== id));
  }
};

export const notificationHistory = {
  subscribe: history.subscribe,
  markAllRead() {
    history.update(entries => entries.map(entry => ({ ...entry, read: true })));
  },
  clear() {
    history.set([]);
  }
};
