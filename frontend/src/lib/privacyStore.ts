import { writable } from 'svelte/store';

const STORAGE_KEY = 'lmz:privacy-blur';

function readInitialPrivacyBlur() {
  if (typeof localStorage === 'undefined') return false;
  return localStorage.getItem(STORAGE_KEY) === '1';
}

export const privacyBlur = writable(readInitialPrivacyBlur());

if (typeof localStorage !== 'undefined') {
  privacyBlur.subscribe((enabled) => {
    localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
  });
}
