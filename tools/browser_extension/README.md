# LMZ Browser Extension

Phase 9 browser capture integration.

Current target:

- Edge first: load `tools/browser_extension/edge/` as an unpacked extension.
- Chrome later with a near-identical Manifest V3 build.
- Firefox later after Chromium flow is stable.

The extension has two flows:

- Capture image: right-click an image, upload it to LMZ capture staging, then commit it with metadata from the popup.
- Online queue: right-click a supported platform page, stage the URL in the popup, then append it to LMZ's online queue with metadata.

The extension stores only lightweight UI state. Backend capture staging sidecars are the source of truth for staged files.
