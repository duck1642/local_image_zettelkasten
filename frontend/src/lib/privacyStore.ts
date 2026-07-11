import { derived } from 'svelte/store';
import { appSettings } from './appSettingsStore';

export const privacyBlur = derived(
  appSettings,
  ($settings) => Boolean($settings?.ui?.privacy_blur)
);
