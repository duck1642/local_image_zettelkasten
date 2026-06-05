# Chrome Extension

This is the Chrome Manifest V3 browser extension for LMZ. It matches the Edge
offline-first capture flow.

## Installation

1. Open Google Chrome.
2. Navigate to `chrome://extensions/`.
3. Enable **Developer mode** in the top right corner.
4. Click **Load unpacked** in the top left corner.
5. Select this directory (`tools/browser_extension/chrome/`).

Pending captures and online queue items are stored locally first, so capture can
continue while LMZ is closed. Sync and commit from the popup after LMZ is open.
