<script lang="ts">
  import { IconInfoCircle, IconKeyboard } from './icons';
</script>

<div class="shortcuts-guide shortcuts-guide-wide">
  <h4 class="settings-section-title">
    <span class="settings-title-icon">
      <IconKeyboard size={14} />
    </span>
    Keyboard Shortcuts & Search Prefixes
  </h4>
  
  <div class="shortcuts-container-grid">
    <!-- Navigation Column -->
    <div class="shortcuts-column">
      <h5>Navigation & Views</h5>
      <div class="shortcut-row"><span class="key">Enter</span><span class="desc">Execute Search</span></div>
      <div class="shortcut-row"><span class="key">F5</span><span class="desc">Refresh Active View</span></div>
      <div class="shortcut-row"><span class="key">Ctrl+F5</span><span class="desc">Full App Reload</span></div>
      <div class="shortcut-row"><span class="key">Esc</span><span class="desc">Close Media Focus</span></div>
      <div class="shortcut-row"><span class="key">W</span><span class="desc">Toggle Wide View</span></div>
      <div class="shortcut-row"><span class="key">F</span><span class="desc">Toggle Fullscreen</span></div>
      <div class="shortcut-row"><span class="key">A</span><span class="desc">Previous Group Item</span></div>
      <div class="shortcut-row"><span class="key">D</span><span class="desc">Next Group Item</span></div>
      <div class="shortcut-row"><span class="key">I</span><span class="desc">Toggle Inspector Panel</span></div>
    </div>

    <!-- Console Commands Column -->
    <div class="shortcuts-column">
      <h5>Vault Commands (/)</h5>
      <div class="shortcuts-list-scroll sleek-scrollbar">
        <div class="shortcut-row"><span class="key">/grid</span><span class="desc">Switch Vault Grid</span></div>
        <div class="shortcut-row"><span class="key">/masonry</span><span class="desc">Switch Vault Masonry</span></div>
        <div class="shortcut-row"><span class="key">/zoom-in</span><span class="desc">Increase Tile Size</span></div>
        <div class="shortcut-row"><span class="key">/zoom-out</span><span class="desc">Decrease Tile Size</span></div>
        <div class="shortcut-row"><span class="key">/toggle-inspector</span><span class="desc">Toggle Inspector</span></div>
        <div class="shortcut-row"><span class="key">/ram-track</span><span class="desc">Toggle RAM Footer</span></div>
        <div class="shortcut-row"><span class="key">/scan-auth</span><span class="desc">Run Auth Scan</span></div>
        <div class="shortcut-row"><span class="key">/cleanup-review</span><span class="desc">Cleanup Review</span></div>
        <div class="shortcut-row"><span class="key">/sort-newest</span><span class="desc">Sort by Newest</span></div>
        <div class="shortcut-row"><span class="key">/sort-oldest</span><span class="desc">Sort by Oldest</span></div>
        <div class="shortcut-row"><span class="key">/sort-artist</span><span class="desc">Sort by Artist</span></div>
        <div class="shortcut-row"><span class="key">/media-all</span><span class="desc">Show All Media</span></div>
        <div class="shortcut-row"><span class="key">/media-image</span><span class="desc">Filter Images</span></div>
        <div class="shortcut-row"><span class="key">/media-video</span><span class="desc">Filter Videos</span></div>
      </div>
    </div>

    <!-- Search Prefixes Column -->
    <div class="shortcuts-column">
      <h5>Search Prefixes</h5>
      <div class="shortcut-row"><span class="key">/</span><span class="desc">Console Prefix</span></div>
      <div class="shortcut-row"><span class="key">a:</span><span class="desc">Artist Prefix</span></div>
      <div class="shortcut-row"><span class="key">p:</span><span class="desc">Platform Prefix</span></div>
      <div class="shortcut-row"><span class="key">t:</span><span class="desc">Topic Prefix</span></div>
      <div class="shortcut-row"><span class="key">#</span><span class="desc">WD Tag Prefix</span></div>
      
      <div class="restart-banner settings-tip">
        <IconInfoCircle size={12} />
        <span><strong>Quick tip:</strong> Type search prefixes inside the main search bar to filter by metadata categories instantly.</span>
      </div>
    </div>
  </div>
</div>
