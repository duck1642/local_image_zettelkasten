# LMZ Browser Extension

Phase 9 browser capture integration.

- Shared source lives in `tools/browser_extension/src/`.
- Run `python tools/browser_extension/scripts/sync_extensions.py` after changing shared extension files.
- Edge: load `tools/browser_extension/edge/` as an unpacked extension.
- Chrome: load `tools/browser_extension/chrome/` as an unpacked extension.
- Firefox: load `tools/browser_extension/firefox/` as a temporary add-on and run a manual smoke test before relying on it.

The extension has two flows:

- Capture image: right-click an image, cache it locally first, then sync it to LMZ capture staging from the popup.
- Online queue: right-click a supported platform page or image, cache the page URL locally, then append it to LMZ's online queue from the popup.

The extension stores pending work in IndexedDB so capture still works while LMZ is closed. Backend capture staging sidecars become the source of truth after a cached capture is synced.

Large image rule:

- Images up to 100 MB are cached automatically.
- Images over 100 MB ask for download fallback or discard.
- Download fallback writes to `Downloads/LMZ Capture/` and is manual recovery, not automatic LMZ sync.

Edge and Chrome use Chromium MV3 service workers. Firefox uses a Manifest V3 event-page background script.
