<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { onDestroy } from 'svelte';
  import { getCurrentWindow } from '@tauri-apps/api/window';
  import { log as uiLog } from './logger';
  import { apiUrl } from './api';
  import { isImageMedia, isVideoMedia } from './media';

  export let item: any;
  export let group: any = null;
  export let mode: 'wide' | 'fullscreen' = 'wide';
  export let startTime: number = 0;
  
  const dispatch = createEventDispatcher();
  let videoElement: HTMLVideoElement;
  const appWindow = getCurrentWindow();

  $: assetUrl = apiUrl(item.url);

  $: currentIndex = group ? group.items.findIndex((i: any) => i.hash === item?.hash) : 0;

  $: handleModeChange(mode);

  function nextItem() {
      if (!group) return;
      const nextIdx = (currentIndex + 1) % group.items.length;
      dispatch('changeItem', group.items[nextIdx]);
  }

  function prevItem() {
      if (!group) return;
      const prevIdx = (currentIndex - 1 + group.items.length) % group.items.length;
      dispatch('changeItem', group.items[prevIdx]);
  }

  async function handleModeChange(newMode: 'wide' | 'fullscreen') {
      uiLog('INFO', `MediaFocus mode changed to: ${newMode}`);
      try {
          if (newMode === 'fullscreen') {
              await appWindow.setFullscreen(true);
          } else {
              await appWindow.setFullscreen(false);
          }
      } catch (e) {
          console.error('Failed to toggle native fullscreen:', e);
      }
  }

  async function close(reason: string | Event = 'unknown') {
    let reasonStr = typeof reason === 'string' ? reason : 'overlay_or_btn_click';
    uiLog('INFO', `MediaFocus closing because: ${reasonStr}`);
    try {
        await appWindow.setFullscreen(false);
    } catch (e) {
    } finally {
        dispatch('close');
    }
  }

  function handleKeydown(e: KeyboardEvent) {
      if (e.repeat) return;
      const target = e.target as HTMLElement;
      if (['INPUT', 'TEXTAREA'].includes(target.tagName)) return;

      if (e.key === 'Escape') {
          e.preventDefault();
          close('Escape Key Pressed');
      } else if (e.key.toLowerCase() === 'w') {
          e.preventDefault();
          if (mode === 'wide') {
              close('W Key Pressed (Toggle Off Wide)');
          } else {
              uiLog('INFO', 'Dispatching switchMode wide');
              dispatch('switchMode', 'wide');
          }
      } else if (e.key.toLowerCase() === 'f') {
          e.preventDefault();
          if (mode === 'fullscreen') {
              close('F Key Pressed (Toggle Off Fullscreen)');
          } else {
              uiLog('INFO', 'Dispatching switchMode fullscreen');
              dispatch('switchMode', 'fullscreen');
          }
      } else if (e.key.toLowerCase() === 'a') {
          e.preventDefault();
          prevItem();
      } else if (e.key.toLowerCase() === 'd') {
          e.preventDefault();
          nextItem();
      }
  }

  function handleLoaded() {
      if (videoElement && startTime > 0) {
          videoElement.currentTime = startTime;
      }
  }

  onDestroy(async () => {
      try {
          await appWindow.setFullscreen(false);
      } catch(e) {}
  });
</script>

<svelte:window on:keydown={handleKeydown}/>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="focus-overlay" class:fullscreen={mode === 'fullscreen'} on:click={close} on:keydown={handleKeydown} role="button" tabindex="-1">
    {#if group && group.items.length > 1}
        <button class="nav-btn prev" aria-label="Previous item" on:click|stopPropagation={prevItem}>
            <svg viewBox="0 0 24 24" width="40" height="40" stroke="currentColor" stroke-width="3" stroke-linejoin="round" fill="currentColor">
                <path d="M16 4 L6 12 L16 20 Z" />
            </svg>
        </button>
        <button class="nav-btn next" aria-label="Next item" on:click|stopPropagation={nextItem}>
            <svg viewBox="0 0 24 24" width="40" height="40" stroke="currentColor" stroke-width="3" stroke-linejoin="round" fill="currentColor">
                <path d="M8 4 L18 12 L8 20 Z" />
            </svg>
        </button>
    {/if}

    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="media-container" on:click|stopPropagation on:keydown|stopPropagation>
        {#if isImageMedia(item)}
            <img src={assetUrl} alt="Focused View" />
        {:else if isVideoMedia(item)}
            <!-- svelte-ignore a11y-media-has-caption -->
            <video 
                bind:this={videoElement}
                src={assetUrl} 
                controls 
                controlslist="nofullscreen"
                autoplay 
                loop
                on:loadedmetadata={handleLoaded}
            ></video>
        {:else}
            <div class="unsupported-media">Unknown media type</div>
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
    .unsupported-media {
        min-width: 320px;
        min-height: 180px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--text-muted);
        border: 1px solid var(--border-dim);
        border-radius: 8px;
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

    .nav-btn {
        position: absolute;
        top: 50%;
        transform: translateY(-50%);
        background: transparent;
        border: none;
        color: white;
        opacity: 0.15;
        cursor: pointer;
        padding: 20px;
        transition: opacity 0.2s, transform 0.2s;
        z-index: 1010;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .nav-btn:hover {
        opacity: 0.8;
        transform: translateY(-50%) scale(1.1);
    }

    .nav-btn.prev {
        left: 20px;
    }

    .nav-btn.next {
        right: 20px;
    }
</style>

