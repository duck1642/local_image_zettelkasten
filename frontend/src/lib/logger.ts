/**
 * Global logging utility for the Svelte frontend.
 * Sends logs to the Python backend to be recorded in ui.log.
 */
export async function log(level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG', message: string, extra: object = {}) {
    // Print to browser console too
    const colors = { INFO: '#238636', WARNING: '#d29922', ERROR: '#da3633', DEBUG: '#8b949e' };
    console.log(`%c[${level}] %c${message}`, `color: ${colors[level]}; font-weight: bold;`, 'color: inherit;', extra);

    try {
        await apiFetch('/api/logs/ui', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level, message, extra })
        });
    } catch (e) {
        // Silently fail if backend is down
    }
}
import { apiFetch } from './api';
