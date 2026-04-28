<script lang="ts">
    import type { VaultItem } from './types';
    import { assetUrl } from './api';
    export let item: VaultItem;
    
    $: thumbnailUrl = assetUrl(item.thumbnail_url);
    $: fullUrl = assetUrl(item.url);
</script>

<div class="tile">
    {#if item.mime_type.startsWith('image/')}
        <img src={thumbnailUrl} alt={item.original_filename} loading="lazy"
             width={item.width || undefined} height={item.height || undefined} />
    {:else if item.mime_type.startsWith('video/')}
        <video src={fullUrl} poster={thumbnailUrl} preload="none" muted loop
               on:mouseenter={(e) => e.currentTarget.play().catch(() => {})}
               on:mouseleave={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}></video>
        <div class="video-badge">VIDEO</div>
    {/if}
    <div class="info">
        <span class="hash">{item.hash.substring(0, 12)}</span>
        <span class="artist">{item.artist || 'Unknown'}</span>
    </div>
</div>

<style>
    .tile {
        position: relative;
        background: var(--bg-panel);
        border: 1px solid var(--border-dim);
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 10px;
        break-inside: avoid;
        display: flex;
        flex-direction: column;
        transition: border-color 0.2s;
        content-visibility: auto;
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

    .info {
        padding: 8px;
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
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 60%;
        text-align: right;
    }
</style>
