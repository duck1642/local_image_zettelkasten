# LMZ Browser Extension

Phase 9 browser capture integration.

- Edge: load `tools/browser_extension/edge/` as an unpacked extension. This is the active offline-first target.
- Chrome: load `tools/browser_extension/chrome/` as an unpacked extension.
- Firefox: load `tools/browser_extension/firefox/` as a temporary add-on.

The extension has two flows:

- Capture image: right-click an image, cache it locally first, then sync it to LMZ capture staging from the popup.
- Online queue: right-click a supported platform page or image, cache the page URL locally, then append it to LMZ's online queue from the popup.

The Edge extension stores pending work in IndexedDB so capture still works while LMZ is closed. Backend capture staging sidecars become the source of truth after a cached capture is synced.

Large image rule:

- Images up to 100 MB are cached automatically.
- Images over 100 MB ask for download fallback or discard.
- Download fallback writes to `Downloads/LMZ Capture/` and is manual recovery, not automatic LMZ sync.

Chrome and Firefox may lag Edge while the MVP is being tested.
