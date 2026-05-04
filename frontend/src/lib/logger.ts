import { apiFetch } from './api';

type LogLevel = 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
type LogEntry = { level: LogLevel; message: string; extra: object };

const colors: Record<LogLevel, string> = {
    INFO: '#238636',
    WARNING: '#d29922',
    ERROR: '#da3633',
    DEBUG: '#8b949e'
};

let queue: LogEntry[] = [];
let flushTimer: number | null = null;
const FLUSH_INTERVAL_MS = 300;

async function sendBatch(entries: LogEntry[]) {
    if (entries.length === 0) return;
    try {
        // Send entries individually to match existing /api/logs/ui contract
        // (backend expects single entry, not array — batch just reduces call frequency)
        for (const entry of entries) {
            await apiFetch('/api/logs/ui', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(entry)
            });
        }
    } catch (e) {
        // Swallow — logging should never break the app
    }
}

function scheduleFlush() {
    if (flushTimer !== null) return;
    flushTimer = window.setTimeout(() => {
        flushTimer = null;
        const batch = queue;
        queue = [];
        sendBatch(batch);
    }, FLUSH_INTERVAL_MS);
}

export function flushLogs() {
    if (flushTimer !== null) {
        window.clearTimeout(flushTimer);
        flushTimer = null;
    }
    const batch = queue;
    queue = [];
    sendBatch(batch);
}

export async function log(level: LogLevel, message: string, extra: object = {}) {
    // Drop DEBUG in production
    if (level === 'DEBUG' && !import.meta.env.DEV) return;

    console.log(`%c[${level}] %c${message}`, `color: ${colors[level]}; font-weight: bold;`, 'color: inherit;', extra);

    const entry: LogEntry = { level, message, extra };

    if (level === 'ERROR') {
        // ERROR bypasses the queue — flush immediately
        const batch = queue;
        queue = [];
        if (flushTimer !== null) {
            window.clearTimeout(flushTimer);
            flushTimer = null;
        }
        sendBatch([...batch, entry]);
    } else {
        queue.push(entry);
        scheduleFlush();
    }
}
