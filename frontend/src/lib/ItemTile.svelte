<script lang="ts">
    import type { VaultItem } from './types';
    export let item: VaultItem;
    
    // The backend serves assets at http://localhost:8000/vault/...
    const assetUrl = `http://localhost:8000${item.url}`;
</script>

<div class="tile">
    {#if item.mime_type.startsWith('image/')}
        <img src={assetUrl} alt={item.original_filename} loading="lazy" />
    {:else if item.mime_type.startsWith('video/')}
        <video src={assetUrl} muted loop on:mouseenter={e => e.target.play()} on:mouseleave={e => {e.target.pause(); e.target.currentTime = 0}}></video>
        <div class="video-badge">VIDEO</div>
    {/if}
    <div class="info">
        <span class="hash">{item.hash.substring(0, 12)}</span>
        <span class="artist">{item.artist || 'Unknown'}</span>
    </div>
</div>

<style>
    .tile {
        background: var(--bg-panel);
        border: 1px solid var(--border-dim);
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 10px;
        break-inside: avoid;
        transition: border-color 0.2s;
    }

    .tile:hover {
        border-color: var(--border-hover);
    }

    img, video {
        width: 100%;
        display: block;
        height: auto;
    }

    .video-badge {
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(0,0,0,0.6);
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: bold;
    }

    .tile {
        position: relative;
        background: var(--bg-panel);
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 11px;
    }

    .hash {
        color: var(--text-muted);
        font-family: monospace;
    }

    .artist {
        color: var(--accent-purple);
        font-weight: bold;
    }
</style>
