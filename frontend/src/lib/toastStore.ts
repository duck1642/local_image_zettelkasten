import { writable } from 'svelte/store';

export type ToastType = 'success' | 'warning' | 'error' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message: string;
  duration?: number;
}

const { subscribe, update } = writable<Toast[]>([]);

export const toastStore = {
  subscribe,
  add(toast: Omit<Toast, 'id'>) {
    const id = Math.random().toString(36).slice(2, 9);
    const duration = toast.duration ?? 4000;
    update(toasts => {
      const next = [...toasts, { ...toast, id, duration }];
      if (next.length > 3) {
        return next.slice(next.length - 3);
      }
      return next;
    });
    
    if (duration > 0) {
      setTimeout(() => {
        this.dismiss(id);
      }, duration);
    }
    return id;
  },
  dismiss(id: string) {
    update(toasts => toasts.filter(t => t.id !== id));
  }
};
