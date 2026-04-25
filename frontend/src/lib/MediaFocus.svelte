<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { onMount, onDestroy } from 'svelte';
  import { getCurrentWindow } from '@tauri-apps/api/window';

  export let item: any;
  export let mode: 'wide' | 'fullscreen' = 'wide';
  export let startTime: number = 0;
  
  const dispatch = createEventDispatcher();
  let videoElement: HTMLVideoElement;
  const appWindow = getCurrentWindow();

  $: assetUrl = `http://localhost:8000${item.url}`;

  async function close() {
    try {
        if (mode === 'fullscreen') {
            await appWindow.setFullscreen(false);
        }
    } catch (e) {
        console.error('Failed to exit native fullscreen:', e);
    } finally {
        dispatch('close');
    }
  }

  function handleKeydown(e: KeyboardEvent) {
      if (e.key === 'Escape') close();
  }

  function handleLoaded() {
      if (videoElement && startTime > 0) {
          videoElement.currentTime = startTime;
      }
  }

  onMount(async () => {
      if (mode === 'fullscreen') {
          await appWindow.setFullscreen(true);
      }
  });

  onDestroy(async () => {
      await appWindow.setFullscreen(false);
  });
</script>

<svelte:window on:keydown={handleKeydown}/>

<div class="focus-overlay" class:fullscreen={mode === 'fullscreen'} on:click={close}>
    <div class="media-container" on:click|stopPropagation>
        {#if item.mime_type.startsWith('image/')}
            <img src={assetUrl} alt="Focused View" />
        {:else}
            <video 
                bind:this={videoElement}
                src={assetUrl} 
                controls 
                controlslist="nofullscreen"
                autoplay 
                loop
                on:loadedmetadata={handleLoaded}
            ></video>
        {/if}
        
        <div class="controls">
            <button class="close-btn" on:click={close}>Exit {mode === 'fullscreen' ? 'Fullscreen' : 'Wide View'}</button>
        </div>
    </div>
</div>

<style>
    .focus-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0,0,0,0.9);
        z-index: 1000;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 40px;
    }

    .focus-overlay.fullscreen {
        padding: 0;
        background: #000;
    }

    .media-container {
        position: relative;
        max-width: 100%;
        max-height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    img, video {
        max-width: 100%;
        max-height: calc(100vh - 140px);
        box-shadow: 0 0 50px rgba(0,0,0,0.5);
        object-fit: contain;
    }

    .fullscreen img, .fullscreen video {
        max-height: 100vh;
        width: 100vw;
        object-fit: contain;
    }

    .controls {
        margin-top: 20px;
    }

    .fullscreen .controls {
        position: fixed;
        top: -12px;
        right: 8px;
        opacity: 0;
        transition: opacity 0.3s;
        z-index: 1001;
    }

    .fullscreen.focus-overlay:hover .controls,
    .fullscreen .media-container:hover .controls {
        opacity: 1;
    }

    .close-btn {
        background: rgba(0,0,0,0.6);
        border: 1px solid rgba(255,255,255,0.2);
        color: white;
        padding: 8px 20px;
        border-radius: 6px;
        font-weight: bold;
        cursor: pointer;
    }

    .close-btn:hover {
        background: var(--accent-primary);
        border-color: var(--accent-primary);
    }
</style>
