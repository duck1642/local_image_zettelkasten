<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { getCurrentWindow } from '@tauri-apps/api/window';
  import { log as uiLog } from './logger';
  import { apiUrl } from './api';
  import { isImageMedia, isVideoMedia } from './media';

  export let item: any;
  export let group: any = null;
  export let mode: 'wide' | 'fullscreen' = 'wide';
  export let startTime: number = 0;
  
  const dispatch = createEventDispatcher();
  const appWindow = getCurrentWindow();
  const MIN_SCALE = 1;
  const MAX_SCALE = 6;
  const KEYBOARD_STEP = 0.25;

  let videoElement: HTMLVideoElement;
  let mediaFrameEl: HTMLElement;
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let isDragging = false;
  let pointerMoved = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOriginX = 0;
  let dragOriginY = 0;
  let filmstripOpen = false;
  let appliedMode: 'wide' | 'fullscreen' | '' = '';
  let activeHash = '';

  $: assetUrl = item?.url ? apiUrl(item.url) : '';
  $: currentIndex = group ? group.items.findIndex((i: any) => i.hash === item?.hash) : 0;
  $: hasGroupFilmstrip = Boolean(group && group.items?.length > 1);
  $: mediaTransform = mode === 'fullscreen' ? `translate(${translateX}px, ${translateY}px) scale(${scale})` : 'none';
  $: if (item?.hash && item.hash !== activeHash) {
    activeHash = item.hash;
    resetZoom();
  }
  $: if (mode !== appliedMode) {
    appliedMode = mode;
    if (mode !== 'fullscreen') resetZoom();
    handleModeChange(mode);
  }

  function clampScale(value: number) {
    return Math.max(MIN_SCALE, Math.min(MAX_SCALE, value));
  }

  function resetZoom() {
    scale = 1;
    translateX = 0;
    translateY = 0;
    isDragging = false;
    pointerMoved = false;
  }

  function zoomAt(clientX: number, clientY: number, nextScaleValue: number) {
    if (mode !== 'fullscreen' || !mediaFrameEl) return;
    const nextScale = clampScale(nextScaleValue);
    if (nextScale === scale) return;
    const rect = mediaFrameEl.getBoundingClientRect();
    const anchorX = clientX - rect.left - rect.width / 2;
    const anchorY = clientY - rect.top - rect.height / 2;
    const ratio = nextScale / scale;
    translateX = anchorX - (anchorX - translateX) * ratio;
    translateY = anchorY - (anchorY - translateY) * ratio;
    scale = nextScale;
    if (scale === 1) {
      translateX = 0;
      translateY = 0;
    }
  }

  function zoomFromCenter(delta: number) {
    if (!mediaFrameEl) return;
    const rect = mediaFrameEl.getBoundingClientRect();
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, scale + delta);
  }

  function handleWheel(event: WheelEvent) {
    if (mode !== 'fullscreen' || !event.ctrlKey) return;
    event.preventDefault();
    const nextScale = event.deltaY < 0 ? scale * 1.12 : scale / 1.12;
    zoomAt(event.clientX, event.clientY, nextScale);
  }

  function handlePointerDown(event: PointerEvent) {
    if (mode !== 'fullscreen' || scale <= 1) return;
    const target = event.target as HTMLElement;
    if (target.closest('button, input, select, textarea') || target.tagName === 'VIDEO') return;
    event.preventDefault();
    isDragging = true;
    pointerMoved = false;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    dragOriginX = translateX;
    dragOriginY = translateY;
    mediaFrameEl?.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent) {
    if (!isDragging) return;
    const dx = event.clientX - dragStartX;
    const dy = event.clientY - dragStartY;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) pointerMoved = true;
    translateX = dragOriginX + dx;
    translateY = dragOriginY + dy;
  }

  function handlePointerUp(event: PointerEvent) {
    if (!isDragging) return;
    isDragging = false;
    mediaFrameEl?.releasePointerCapture(event.pointerId);
  }

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

  function changeTo(entry: any) {
    dispatch('changeItem', entry);
  }

  async function handleModeChange(newMode: 'wide' | 'fullscreen') {
    uiLog('INFO', `MediaFocus mode changed to: ${newMode}`);
    try {
      await appWindow.setFullscreen(newMode === 'fullscreen');
    } catch (error) {
      uiLog('ERROR', 'Failed to toggle native fullscreen', { error: String(error) });
    }
  }

  async function close(reason: string | Event = 'unknown') {
    const reasonStr = typeof reason === 'string' ? reason : 'overlay_or_btn_click';
    uiLog('INFO', `MediaFocus closing because: ${reasonStr}`);
    try {
      await appWindow.setFullscreen(false);
    } catch {
    } finally {
      dispatch('close');
    }
  }

  function handleOverlayClick(event: MouseEvent) {
    if (event.target !== event.currentTarget) return;
    if (mode === 'fullscreen' && scale !== 1) return;
    if (pointerMoved) return;
    close(event);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.repeat) return;
    const target = e.target as HTMLElement;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;

    if (e.key === 'Escape') {
      e.preventDefault();
      close('Escape Key Pressed');
    } else if (mode === 'fullscreen' && (e.key === '+' || e.key === '=' || e.code === 'NumpadAdd')) {
      e.preventDefault();
      zoomFromCenter(KEYBOARD_STEP);
    } else if (mode === 'fullscreen' && (e.key === '-' || e.code === 'NumpadSubtract')) {
      e.preventDefault();
      zoomFromCenter(-KEYBOARD_STEP);
    } else if (e.key.toLowerCase() === 'w') {
      e.preventDefault();
      if (mode === 'wide') {
        close('W Key Pressed (Toggle Off Wide)');
      } else {
        dispatch('switchMode', 'wide');
      }
    } else if (e.key.toLowerCase() === 'f') {
      e.preventDefault();
      if (mode === 'fullscreen') {
        close('F Key Pressed (Toggle Off Fullscreen)');
      } else {
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

  function thumbnailUrl(entry: any) {
    return apiUrl(entry.thumbnail_url || entry.url);
  }

  onDestroy(async () => {
    try {
      await appWindow.setFullscreen(false);
    } catch {}
  });
</script>

<svelte:window on:keydown={handleKeydown}/>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
  class="focus-overlay"
  class:fullscreen={mode === 'fullscreen'}
  on:click={handleOverlayClick}
  on:keydown={handleKeydown}
  on:wheel={handleWheel}
  role="button"
  tabindex="-1"
>
  {#if hasGroupFilmstrip}
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
  <div class="media-container" class:filmstrip-open={filmstripOpen && hasGroupFilmstrip} on:click|stopPropagation on:keydown|stopPropagation>
    <div
      class="media-frame"
      class:zoomed={mode === 'fullscreen' && scale > 1}
      class:dragging={isDragging}
      bind:this={mediaFrameEl}
      style={`transform: ${mediaTransform};`}
      on:pointerdown={handlePointerDown}
      on:pointermove={handlePointerMove}
      on:pointerup={handlePointerUp}
      on:pointercancel={handlePointerUp}
      on:dblclick|preventDefault={resetZoom}
    >
      {#if isImageMedia(item)}
        <img class="focus-media" src={assetUrl} alt="Focused View" draggable="false" />
      {:else if isVideoMedia(item)}
        <!-- svelte-ignore a11y-media-has-caption -->
        <video 
          class="focus-media"
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
    </div>

    <div class="controls">
      <button class="close-btn" on:click={close}>Exit {mode === 'fullscreen' ? 'Fullscreen' : 'Wide View'}</button>
    </div>
  </div>

  {#if hasGroupFilmstrip}
    <button class="filmstrip-toggle" aria-label="Toggle filmstrip" on:click|stopPropagation={() => filmstripOpen = !filmstripOpen}>
      {filmstripOpen ? 'v' : '^'}
    </button>
    {#if filmstripOpen}
      <div class="filmstrip" on:click|stopPropagation on:keydown|stopPropagation>
        <div class="filmstrip-row">
          {#each group.items as entry, index (entry.hash)}
            <button
              class="filmstrip-thumb"
              class:active={entry.hash === item?.hash}
              title={`${index + 1} / ${group.items.length}`}
              on:click={() => changeTo(entry)}
            >
              <img src={thumbnailUrl(entry)} alt="" draggable="false" />
            </button>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
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
    overflow: hidden;
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
    justify-content: center;
    overflow: visible;
  }

  .media-container.filmstrip-open {
    max-height: calc(100vh - 118px);
  }

  .media-frame {
    display: flex;
    align-items: center;
    justify-content: center;
    transform-origin: center center;
  }

  .media-frame.zoomed {
    cursor: grab;
  }

  .media-frame.dragging {
    cursor: grabbing;
  }

  .focus-media {
    max-width: 100%;
    max-height: calc(100vh - 140px);
    box-shadow: 0 0 50px rgba(0,0,0,0.5);
    object-fit: contain;
    user-select: none;
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

  .fullscreen .focus-media {
    max-width: 100vw;
    max-height: 100vh;
    width: 100vw;
    object-fit: contain;
  }

  .fullscreen .media-container.filmstrip-open .focus-media {
    max-height: calc(100vh - 118px);
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

  .filmstrip-toggle {
    position: fixed;
    left: 50%;
    bottom: 16px;
    transform: translateX(-50%);
    z-index: 1020;
    min-width: 36px;
    height: 28px;
    border-radius: 999px;
    background: rgba(13, 17, 23, 0.82);
    border: 1px solid rgba(255,255,255,0.25);
    color: var(--text-main);
    cursor: pointer;
  }

  .filmstrip {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    height: 96px;
    z-index: 1015;
    background: rgba(13, 17, 23, 0.94);
    border-top: 1px solid rgba(255,255,255,0.12);
    display: flex;
    align-items: center;
    padding: 10px 54px;
    box-sizing: border-box;
  }

  .filmstrip-row {
    display: flex;
    align-items: center;
    gap: 10px;
    overflow-x: auto;
    overflow-y: hidden;
    width: 100%;
    height: 100%;
  }

  .filmstrip-thumb {
    width: 64px;
    height: 72px;
    flex: 0 0 auto;
    padding: 2px;
    border-radius: 6px;
    border: 2px solid transparent;
    background: rgba(255,255,255,0.06);
    cursor: pointer;
  }

  .filmstrip-thumb.active {
    border-color: var(--accent-primary);
  }

  .filmstrip-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 4px;
    display: block;
  }
</style>
