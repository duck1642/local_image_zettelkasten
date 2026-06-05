# Firefox Extension

This is the Firefox Manifest V3 browser extension for LMZ. It uses the shared
offline-first capture flow with a Firefox event-page background script.

## Installation

1. Open Firefox.
2. Navigate to `about:debugging#/runtime/this-firefox`.
3. Click **Load Temporary Add-on...**
4. Select the `manifest.json` file in this directory (`tools/browser_extension/firefox/manifest.json`).

Pending captures and online queue items are stored locally first, so capture can
continue while LMZ is closed. Sync and commit from the popup after LMZ is open.
