<script lang="ts">
  import type { VaultItem } from './types';
  import { createEventDispatcher, onDestroy, tick } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';
  import { isImageMedia, isVideoMedia } from './media';
  import { runtimeSessionKey } from './runtimeStore';
  import MetadataActionModal from './stats/MetadataActionModal.svelte';
  import { renameTopic } from './stats/statsApi';

  export let item: VaultItem | null = null;
  export let group: { id: string, items: VaultItem[] } | null = null;
  export let focusMode: 'normal' | 'wide' | 'fullscreen' = 'normal';
  export let width = 400;
  const dispatch = createEventDispatcher();

  let fullItem: any = null;
  let artist = '';
  let savedArtist = '';
  let sourceUrl = '';
  let platform = '';
  let topics: string[] = [];
  let savedTopics: string[] = [];
  let draftTopics: string[] = [];
  let topicInputOpen = false;
  let topicInputValue = '';
  let topicInputElement: HTMLInputElement | undefined;
  let topicSuggestions: { value: string; count?: number }[] = [];
  let topicSuggestionsOpen = false;
  let topicSuggestionsLoading = false;
  let activeTopicSuggestionIndex = -1;
  let topicSuggestionTimer: number | null = null;
  let topicSuggestionAbortController: AbortController | null = null;
  let savedWdRating = '';
  let draftWdRating = '';
  let savedWdCharacters: string[] = [];
  let draftWdCharacters: string[] = [];
  let savedWdGeneral: string[] = [];
  let draftWdGeneral: string[] = [];
  let isDirty = false;
  let loading = false;
  let loadingTimeout: any = null;
  let showLoadingIndicator = false;
  let tagging = false;
  let abortController: AbortController | null = null;
  let lastLoadedHash: string | null = null;
  let currentRuntimeSessionKey = '';

  // Topic Rename Modal State
  let renameModalOpen = false;
  let renameModalValue = '';
  let renameModalNewValue = '';
  let renameModalBusy = false;
  let renameModalResult = '';
  let renameModalError = '';

  function openRenameTopicModal(topic: string) {
    renameModalOpen = true;
    renameModalValue = topic;
    renameModalNewValue = topic;
    renameModalBusy = false;
    renameModalResult = '';
    renameModalError = '';
  }

  function closeRenameTopicModal() {
    if (renameModalBusy) return;
    renameModalOpen = false;
    renameModalValue = '';
    renameModalNewValue = '';
    renameModalResult = '';
    renameModalError = '';
  }

  async function confirmRenameTopic() {
    if (!renameModalValue || !renameModalNewValue.trim()) return;
    renameModalBusy = true;
    renameModalResult = '';
    renameModalError = '';
    try {
      const payload = await renameTopic(renameModalValue, renameModalNewValue);
      const newLabel = String(payload.new_label || renameModalNewValue.trim());
      
      // Update draftTopics, savedTopics, topics in local state
      draftTopics = draftTopics.map((t) => t === renameModalValue ? newLabel : t);
      savedTopics = savedTopics.map((t) => t === renameModalValue ? newLabel : t);
      topics = [...draftTopics];
      
      // If fullItem holds details, refresh counts or update fullItem.topics
      if (fullItem && Array.isArray(fullItem.topics)) {
        fullItem.topics = fullItem.topics.map((t: string) => t === renameModalValue ? newLabel : t);
        if (fullItem.topic_counts) {
          const count = fullItem.topic_counts[renameModalValue];
          delete fullItem.topic_counts[renameModalValue];
          if (count !== undefined) {
            fullItem.topic_counts[newLabel] = count;
          }
        }
      }
      
      const vaultCount = Array.isArray(payload?.vaults_touched) ? payload.vaults_touched.length : 0;
      renameModalResult = `Renamed topic across ${payload.notes_rewritten || 0} notes in ${vaultCount} vaults.`;
      
      // Log maintenance action
      uiLog('INFO', 'Topic renamed from inspector', {
        oldValue: renameModalValue,
        newValue: newLabel,
        notes: payload.notes_rewritten
      });
      
      // Dispatch global refresh events
      window.dispatchEvent(new CustomEvent('lmz:refresh', { detail: { tab: 'stats' } }));
      window.dispatchEvent(new CustomEvent('lmz:refresh', { detail: { tab: 'vault' } }));
    } catch (err) {
      renameModalError = `Failed to rename topic: ${String(err)}`;
      uiLog('ERROR', 'Failed to rename topic from inspector', {
        value: renameModalValue,
        error: String(err)
      });
    } finally {
      renameModalBusy = false;
    }
  }

  let videoElement: HTMLVideoElement | undefined;

  $: if (item) {
      if (item.hash !== lastLoadedHash) loadFullDetails(item.hash);
  } else {
      clearDetails();
  }
  $: if ($runtimeSessionKey) {
      if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) clearDetails(true);
      currentRuntimeSessionKey = $runtimeSessionKey;
  }

  $: currentIndex = group ? group.items.findIndex(i => i.hash === item?.hash) : 0;
  $: metadataDirty = !sameStringList(draftTopics, savedTopics)
    || draftWdRating !== savedWdRating
    || !sameStringList(draftWdCharacters, savedWdCharacters)
    || !sameStringList(draftWdGeneral, savedWdGeneral);
  $: isDirty = Boolean(fullItem && (artist !== savedArtist || metadataDirty));

  async function loadFullDetails(hash: string) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const signal = abortController.signal;
    
    if (loadingTimeout) {
      clearTimeout(loadingTimeout);
      loadingTimeout = null;
    }
    
    loading = true;
    showLoadingIndicator = false;
    
    // Only trigger loading overlay and clear details if it takes longer than 200ms
    loadingTimeout = setTimeout(() => {
      showLoadingIndicator = true;
      fullItem = null;
    }, 200);

    try {
        const res = await apiFetch(`/api/items/${hash}`, { signal });
        if (!res.ok) throw new Error('API error');
        const detail = await res.json();

        if (loadingTimeout) {
          clearTimeout(loadingTimeout);
          loadingTimeout = null;
        }
        showLoadingIndicator = false;

        applyLoadedDetails(detail);
        lastLoadedHash = hash;
    } catch (e: any) {
        if (e.name !== 'AbortError') {
            if (loadingTimeout) {
              clearTimeout(loadingTimeout);
              loadingTimeout = null;
            }
            showLoadingIndicator = false;
            fullItem = null;
            uiLog('ERROR', 'Failed to load item details', { hash, error: String(e) });
        }
    } finally {
        if (!signal.aborted) {
            loading = false;
        }
    }
  }

  function handleInput() {}

  function normalizeList(values: unknown): string[] {
    if (!Array.isArray(values)) return [];
    const seen = new Set<string>();
    const result: string[] = [];
    for (const value of values) {
      const clean = String(value || '').trim();
      const key = clean.toLocaleLowerCase();
      if (!clean || seen.has(key)) continue;
      seen.add(key);
      result.push(clean);
    }
    return result;
  }

  function clearDetails(abort = false) {
    if (abort) abortController?.abort();
    if (loadingTimeout) {
      clearTimeout(loadingTimeout);
      loadingTimeout = null;
    }
    showLoadingIndicator = false;
    fullItem = null;
    artist = '';
    savedArtist = '';
    sourceUrl = '';
    platform = '';
    topics = [];
    savedTopics = [];
    draftTopics = [];
    topicInputOpen = false;
    topicInputValue = '';
    clearTopicSuggestions();
    savedWdRating = '';
    draftWdRating = '';
    savedWdCharacters = [];
    draftWdCharacters = [];
    savedWdGeneral = [];
    draftWdGeneral = [];
    loading = false;
    tagging = false;
    lastLoadedHash = null;
  }

  function sameStringList(a: string[], b: string[]) {
    if (a.length !== b.length) return false;
    return a.every((value, index) => value === b[index]);
  }

  function applyLoadedDetails(detail: any) {
    fullItem = detail;
    savedArtist = detail.artist || '';
    artist = savedArtist;
    sourceUrl = detail.source_url || '';
    platform = detail.platform || '';
    savedTopics = normalizeList(detail.topics || []);
    draftTopics = [...savedTopics];
    topics = draftTopics;
    savedWdRating = detail.wd_tags?.rating && detail.wd_tags.rating !== 'None' ? String(detail.wd_tags.rating) : '';
    draftWdRating = savedWdRating;
    savedWdCharacters = normalizeList(detail.wd_tags?.characters || []);
    draftWdCharacters = [...savedWdCharacters];
    savedWdGeneral = normalizeList(detail.wd_tags?.general || []);
    draftWdGeneral = [...savedWdGeneral];
  }

  function countFor(map: Record<string, number> | undefined, value: string) {
    const count = map?.[value];
    return typeof count === 'number' && count > 0 ? count : null;
  }

  function isUnsavedTopic(value: string) {
    const key = value.toLocaleLowerCase();
    return !savedTopics.some((topic) => topic.toLocaleLowerCase() === key);
  }

  function isTagPromoted(value: string) {
    if (!value) return false;
    const key = value.toLocaleLowerCase();
    return draftTopics.some((topic) => topic.toLocaleLowerCase() === key) &&
           !savedTopics.some((topic) => topic.toLocaleLowerCase() === key);
  }

  function normalizeTopicLabel(value: string) {
    const cleaned = String(value || '')
      .trim()
      .toLocaleLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .replace(/_+/g, '_');
    return cleaned || 'topic';
  }

  function isAlreadyTopic(value: string) {
    if (!value) return false;
    const clean = normalizeTopicLabel(value);
    const key = clean.toLocaleLowerCase();
    return savedTopics.some((topic) => topic.toLocaleLowerCase() === key);
  }

  function promoteWdToTopic(value: string) {
    const clean = normalizeTopicLabel(value);
    if (!clean) return;
    const key = clean.toLocaleLowerCase();
    
    // Guard: If this normalized name is already a saved topic, do nothing.
    if (savedTopics.some((topic) => topic.toLocaleLowerCase() === key)) {
      return;
    }
    
    if (draftTopics.some((topic) => topic.toLocaleLowerCase() === key)) {
      removeDraftTopic(clean);
      return;
    }
    draftTopics = [...draftTopics, clean];
    topics = draftTopics;
  }

  async function openTopicInput() {
    topicInputOpen = true;
    await tick();
    topicInputElement?.focus();
    fetchTopicSuggestions('');
  }

  function clearTopicSuggestions() {
    if (topicSuggestionTimer !== null) {
      window.clearTimeout(topicSuggestionTimer);
      topicSuggestionTimer = null;
    }
    topicSuggestionAbortController?.abort();
    topicSuggestionAbortController = null;
    topicSuggestions = [];
    topicSuggestionsOpen = false;
    topicSuggestionsLoading = false;
    activeTopicSuggestionIndex = -1;
  }

  function normalizeTopicKey(value: string) {
    return normalizeTopicLabel(value).toLocaleLowerCase();
  }

  function availableTopicSuggestions(items: { value: string; count?: number }[]) {
    const existing = new Set(draftTopics.map((topic) => topic.toLocaleLowerCase()));
    return items
      .filter((item) => item.value && !existing.has(normalizeTopicKey(item.value)))
      .slice(0, 8);
  }

  async function fetchTopicSuggestions(query: string) {
    topicSuggestionAbortController?.abort();
    topicSuggestionAbortController = new AbortController();
    topicSuggestionsLoading = true;
    try {
      const params = new URLSearchParams({
        kind: 'topic',
        q: query.trim(),
        scope: 'all',
        limit: '8'
      });
      const response = await apiFetch(`/api/facets?${params.toString()}`, {
        signal: topicSuggestionAbortController.signal
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const items = Array.isArray(data.items) ? data.items : [];
      topicSuggestions = availableTopicSuggestions(items.map((item: any) => ({
        value: String(item.value || ''),
        count: Number(item.count || 0)
      })));
      topicSuggestionsOpen = topicInputOpen && topicSuggestions.length > 0;
      activeTopicSuggestionIndex = topicSuggestions.length > 0 ? 0 : -1;
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        topicSuggestions = [];
        topicSuggestionsOpen = false;
        uiLog('ERROR', 'Failed to load topic suggestions', { error: String(error) });
      }
    } finally {
      topicSuggestionsLoading = false;
    }
  }

  function queueTopicSuggestions() {
    if (topicSuggestionTimer !== null) window.clearTimeout(topicSuggestionTimer);
    topicSuggestionTimer = window.setTimeout(() => {
      topicSuggestionTimer = null;
      fetchTopicSuggestions(topicInputValue);
    }, 150);
  }

  function addTopicValue(value: string) {
    const clean = normalizeTopicLabel(value);
    if (!clean) return;
    const key = clean.toLocaleLowerCase();
    if (draftTopics.some((topic) => topic.toLocaleLowerCase() === key)) return;
    draftTopics = [...draftTopics, clean];
    topics = draftTopics;
  }

  function addDraftTopic() {
    const clean = topicSuggestionsOpen && activeTopicSuggestionIndex >= 0
      ? topicSuggestions[activeTopicSuggestionIndex]?.value || topicInputValue
      : topicInputValue;
    topicInputValue = '';
    topicInputOpen = false;
    clearTopicSuggestions();
    addTopicValue(clean);
  }

  function handleTopicInputKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      addDraftTopic();
    } else if (event.key === 'ArrowDown' && topicSuggestionsOpen && topicSuggestions.length > 0) {
      event.preventDefault();
      activeTopicSuggestionIndex = (activeTopicSuggestionIndex + 1) % topicSuggestions.length;
    } else if (event.key === 'ArrowUp' && topicSuggestionsOpen && topicSuggestions.length > 0) {
      event.preventDefault();
      activeTopicSuggestionIndex = (activeTopicSuggestionIndex - 1 + topicSuggestions.length) % topicSuggestions.length;
    } else if (event.key === 'Escape') {
      event.preventDefault();
      topicInputValue = '';
      topicInputOpen = false;
      clearTopicSuggestions();
    }
  }

  function selectTopicSuggestion(value: string) {
    topicInputValue = '';
    topicInputOpen = false;
    clearTopicSuggestions();
    addTopicValue(value);
  }

  function handleTopicInputBlur() {
    if (!topicInputValue.trim()) {
      topicInputOpen = false;
      clearTopicSuggestions();
    }
  }

  function removeDraftTopic(value: string) {
    const key = String(value || '').trim().toLocaleLowerCase();
    draftTopics = draftTopics.filter((topic) => topic.toLocaleLowerCase() !== key);
    topics = draftTopics;
  }

  function removeDraftWdTag(kind: 'rating' | 'character' | 'general', value: string) {
    const key = String(value || '').trim().toLocaleLowerCase();
    if (kind === 'rating' && draftWdRating.toLocaleLowerCase() === key) {
      draftWdRating = '';
    } else if (kind === 'character') {
      draftWdCharacters = draftWdCharacters.filter((tag) => tag.toLocaleLowerCase() !== key);
    } else if (kind === 'general') {
      draftWdGeneral = draftWdGeneral.filter((tag) => tag.toLocaleLowerCase() !== key);
    }
  }

  function stopChipRemove(event: Event) {
    event.preventDefault();
    event.stopPropagation();
  }

  async function revertChanges() {
    if (!item) return;
    await loadFullDetails(item.hash);
  }

  async function responseErrorText(response: Response, fallback: string) {
    try {
      const data = await response.json();
      return data?.detail || data?.message || fallback;
    } catch {
      return fallback;
    }
  }

  function reportActionFailure(action: string, error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    uiLog('ERROR', `${action} failed`, { error: message });
    alert(`${action} failed: ${message}`);
  }

  async function save() {
    if (!item) return;
    try {
      const res = await apiFetch(`/api/items/${item.hash}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          artist,
          topics: draftTopics,
          wd_rating: draftWdRating,
          wd_character_tags: draftWdCharacters,
          wd_tags: draftWdGeneral
        })
      });
      if (!res.ok) throw new Error('Failed to save');
      const detail = await res.json();
      applyLoadedDetails(detail);
      dispatch('updated', { hash: item.hash, artist, source_url: sourceUrl, platform });
      uiLog('INFO', `Metadata saved for ${item.hash.substring(0, 12)}`);
    } catch (e) {
        uiLog('ERROR', 'Save failed', { error: String(e) });
        alert('Failed to save changes.');
    }
  }

  async function runTagging() {
      if (!item || tagging) return;
      tagging = true;
      uiLog('INFO', `Manual tagging started for ${item.hash.substring(0, 12)}`);
      try {
          const res = await apiFetch(`/api/items/${item.hash}/tag`, { method: 'POST' });
          if (!res.ok) {
              const err = await res.json();
              throw new Error(err.detail || 'Tagging failed');
          }
          fullItem = await res.json();
          applyLoadedDetails(fullItem);
          uiLog('INFO', `Tagging complete for ${item.hash.substring(0, 12)}`);
      } catch (e) {
          uiLog('ERROR', 'Tagging failed', { error: String(e) });
          alert(`Tagging failed: ${e}`);
      } finally {
          tagging = false;
      }
  }

  async function openFolder() {
    if (!item) return;
    try {
        const res = await apiFetch(`/api/items/${item.hash}/open_folder`, { method: 'POST' });
        if (!res.ok) throw new Error(await responseErrorText(res, `HTTP ${res.status}`));
        uiLog('INFO', `Opened folder and selected ${item.hash.substring(0, 12)}`);
    } catch (e) { reportActionFailure('Open folder', e); }
  }

  async function openMarkdown() {
    if (!item) return;
    try {
        const res = await apiFetch(`/api/items/${item.hash}/open_note`, { method: 'POST' });
        if (!res.ok) throw new Error(await responseErrorText(res, `HTTP ${res.status}`));
        uiLog('INFO', `Opened markdown note for ${item.hash.substring(0, 12)}`);
    } catch (e) { reportActionFailure('Open note', e); }
  }

  async function copyFile() {
      if (!item) return;
      try {
          const res = await apiFetch(`/api/items/${item.hash}/path`);
          if (!res.ok) throw new Error(await responseErrorText(res, `HTTP ${res.status}`));
          const data = await res.json();
          await invoke('copy_file_to_clipboard', { path: data.absolute_path });
          uiLog('INFO', `File copied to clipboard: ${item.hash.substring(0, 12)}`);
      } catch (e) { reportActionFailure('Copy file', e); }
  }

  async function deleteData() {
      if (!item) return;
      if (!confirm("Are you sure you want to permanently delete this item? This will delete the file, note, and database entry.")) return;
      try {
          const res = await apiFetch(`/api/items/${item.hash}`, { method: 'DELETE' });
          if (res.ok) {
              uiLog('INFO', `Item deleted: ${item.hash}`);
              dispatch('deleted', item.hash);
          } else {
              throw new Error("Failed to delete");
          }
      } catch (e) { uiLog('ERROR', 'Delete failed', { error: String(e) }); }
  }

  function copyHash() {
    if (!item) return;
    navigator.clipboard.writeText(item.hash)
        .then(() => uiLog('DEBUG', 'Hash copied to clipboard'))
        .catch(e => uiLog('ERROR', 'Failed to copy hash', { error: String(e) }));
  }

  function toggleFocus(mode: 'wide' | 'fullscreen') {
      const startTime = videoElement ? videoElement.currentTime : 0;
      dispatch('focus', { mode, hash: item?.hash, startTime });
  }

  function handleKeydown(e: KeyboardEvent) {
      if (!item) return;
      if (e.repeat) return;
      const target = e.target as HTMLElement;
      if (['INPUT', 'TEXTAREA'].includes(target.tagName)) return;

      if (focusMode !== 'normal') return;

      const key = e.key.toLowerCase();
      if (key === 'a') {
          e.preventDefault();
          prevItem();
      } else if (key === 'd') {
          e.preventDefault();
          nextItem();
      } else if (key === 'w') {
          e.preventDefault();
          toggleFocus('wide');
      } else if (key === 'f') {
          e.preventDefault();
          toggleFocus('fullscreen');
      }
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

  onDestroy(() => {
      abortController?.abort();
      clearTopicSuggestions();
  });
</script>

<svelte:window on:keydown={handleKeydown} />

<aside class="inspector" style={`width: ${width}px; min-width: ${width}px;`}>
  {#if !item}
    <div class="empty-panel">
        <p>No item selected</p>
    </div>
  {:else}
    {#if showLoadingIndicator}
      <div class="loading-overlay">
          <p>Loading details...</p>
      </div>
    {/if}
    {#if fullItem}
      <!-- Pinned Header -->
      <div class="inspector-header">
        <div class="group-container media-preview">
            {#if isImageMedia(item)}
                <img src={apiUrl(item.thumbnail_url || item.url)} alt="Preview" />
            {:else if isVideoMedia(item)}
                <!-- svelte-ignore a11y-media-has-caption -->
                <video
                    bind:this={videoElement}
                    src={apiUrl(item.url)}
                    controls
                    controlslist="nofullscreen"
                    muted
                    loop
                    autoplay
                ></video>
            {:else}
                <div class="unsupported-media">Unknown media type</div>
            {/if}
            <div class="media-overlay">
                <button class="overlay-btn" title="Wide View" on:click={() => toggleFocus('wide')}>
                    <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3"></path>
                    </svg>
                </button>
                <button class="overlay-btn" title="Fullscreen" on:click={() => toggleFocus('fullscreen')}>
                    <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                    </svg>
                </button>
            </div>
        </div>

        {#if group && group.items.length > 1}
            <div class="group-nav group-container horizontal">
                <button on:click={prevItem} title="Previous Item">
                    <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                </button>
                <div class="counter">
                    <span class="active-index">{currentIndex + 1}</span>
                    <span class="sep">/</span>
                    <span class="total-count">{group.items.length}</span>
                </div>
                <button on:click={nextItem} title="Next Item">
                    <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </button>
            </div>
        {/if}
      </div>

      <!-- Scrollable Body -->
      <div class="inspector-body">
        <div class="metadata-grid">
          <!-- Artist Row -->
          <span class="grid-label">Artist</span>
          <div class="grid-value">
            <input
              id="inspector-artist"
              type="text"
              bind:value={artist}
              on:input={handleInput}
              placeholder="Unknown Artist"
              class="inline-input"
            />
          </div>

          <!-- Platform Row -->
          <span class="grid-label">Platform</span>
          <div class="grid-value platform-row">
            <span class="platform-text">{platform || 'Unknown'}</span>
          </div>

          <!-- Source URL Row -->
          <span class="grid-label">Source</span>
          <div class="grid-value source-row">
            <input
              type="text"
              bind:value={sourceUrl}
              placeholder="No Source URL"
              readonly
              class="inline-input read-only-input"
            />
            {#if sourceUrl}
              <a href={sourceUrl} target="_blank" rel="noopener noreferrer" class="link-icon-btn" title="Open Source URL: {sourceUrl}">
                <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                  <polyline points="15 3 21 3 21 9"></polyline>
                  <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
              </a>
            {/if}
          </div>

          <!-- Hash Row -->
          <span class="grid-label">Hash</span>
          <div class="grid-value hash-row">
            <span class="hash-text" title={item.hash}>{item.hash}</span>
            <button class="icon-btn-compact" on:click={copyHash} title="Copy Hash">
              <svg viewBox="0 0 24 24" width="11" height="11" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            </button>
          </div>
        </div>

        <div class="group-container horizontal action-toolbar">
          <button class="toolbar-btn" on:click={openFolder} title="Open Folder (Reveal in File Explorer)">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
          </button>
          <button class="toolbar-btn" on:click={openMarkdown} title="Open Note (Open Markdown in Obsidian)">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
          </button>
          <button class="toolbar-btn" on:click={copyFile} title="Copy File to Clipboard">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
            </svg>
          </button>
          <button class="toolbar-btn delete-btn" on:click={deleteData} title="Permanently Delete Media, Note, and Database Record">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>

        <div class="group-container">
          <!-- svelte-ignore a11y-label-has-associated-control -->
          <div class="section-heading">
            <label class="section-label">My Topics</label>
            <button class="add-topic-btn" type="button" title="Add topic" aria-label="Add topic" on:click={openTopicInput}>+</button>
          </div>
          {#if topicInputOpen}
            <div class="topic-input-wrap">
              <div class="topic-input-row">
                <input
                  bind:this={topicInputElement}
                  type="text"
                  class="topic-input"
                  bind:value={topicInputValue}
                  placeholder="Topic"
                  on:input={queueTopicSuggestions}
                  on:focus={() => fetchTopicSuggestions(topicInputValue)}
                  on:keydown={handleTopicInputKeydown}
                  on:blur={handleTopicInputBlur}
                />
                <button class="topic-confirm-btn" type="button" title="Add topic" aria-label="Add topic" on:mousedown|preventDefault on:click={addDraftTopic}>+</button>
              </div>
              {#if topicSuggestionsOpen}
                <div class="topic-suggestions" role="listbox">
                  {#each topicSuggestions as suggestion, index}
                    <button
                      type="button"
                      class:active={index === activeTopicSuggestionIndex}
                      role="option"
                      aria-selected={index === activeTopicSuggestionIndex}
                      on:mousedown|preventDefault
                      on:mouseenter={() => activeTopicSuggestionIndex = index}
                      on:click={() => selectTopicSuggestion(suggestion.value)}
                    >
                      <span>{normalizeTopicLabel(suggestion.value)}</span>
                      {#if suggestion.count}
                        <span class="suggestion-count">{suggestion.count}</span>
                      {/if}
                    </button>
                  {/each}
                </div>
              {:else if topicSuggestionsLoading}
                <div class="topic-suggestions loading">Loading...</div>
              {/if}
            </div>
          {/if}
          <div class="tags-list">
              {#each (draftTopics || []) as tag}
                  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                  <!-- svelte-ignore a11y-no-noninteractive-element-to-interactive-role -->
                  <span 
                      class="tag-chip topic" 
                      class:promoted={isUnsavedTopic(tag)}
                      class:clickable={isUnsavedTopic(tag)}
                      role={isUnsavedTopic(tag) ? "button" : undefined}
                      tabindex={isUnsavedTopic(tag) ? 0 : undefined}
                      title={isUnsavedTopic(tag) ? "Click to revert topic promotion" : undefined}
                      on:click={() => { if (isUnsavedTopic(tag)) removeDraftTopic(tag); }}
                      on:keydown={(event) => { if (isUnsavedTopic(tag) && (event.key === 'Enter' || event.key === ' ')) removeDraftTopic(tag); }}
                  >
                      <span class="tag-label">{tag}</span>
                      {#if countFor(fullItem.topic_counts, tag)}
                          <span class="tag-count">{countFor(fullItem.topic_counts, tag)}</span>
                      {/if}
                      <button class="chip-rename" type="button" title="Rename topic" on:click|stopPropagation={() => openRenameTopicModal(tag)}>
                          <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                      </button>
                      <button class="chip-remove" type="button" title="Remove topic" on:click={(event) => { stopChipRemove(event); removeDraftTopic(tag); }}>
                          <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                      </button>
                  </span>
              {/each}
              {#if !draftTopics || draftTopics.length === 0}
                  <div class="value-text">No topics</div>
              {/if}
          </div>
        </div>

        <div class="group-container">
          <!-- svelte-ignore a11y-label-has-associated-control -->
          <label class="section-label">WD Suggestions</label>
          
          <div class="tags-list suggestions-wrap">
            {#if draftWdRating}
              <span class="tag-chip rating" class:clickable={!isAlreadyTopic(draftWdRating)} class:promoted={isTagPromoted(draftWdRating)} role="button" tabindex="0" title={isAlreadyTopic(draftWdRating) ? "Already a topic" : "Promote to topic"} on:click={() => promoteWdToTopic(draftWdRating)} on:keydown={(event) => { if (event.key === 'Enter' || event.key === ' ') promoteWdToTopic(draftWdRating); }}>
                  <span class="tag-label">{draftWdRating}</span>
                  {#if countFor(fullItem.wd_tag_counts, draftWdRating)}
                      <span class="tag-count">{countFor(fullItem.wd_tag_counts, draftWdRating)}</span>
                  {/if}
                  <button class="chip-remove" type="button" title="Remove WD tag" on:click={(event) => { stopChipRemove(event); removeDraftWdTag('rating', draftWdRating); }}>
                      <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                  </button>
              </span>
            {/if}
            
            {#each (draftWdCharacters || []) as tag}
              <span class="tag-chip character" class:clickable={!isAlreadyTopic(tag)} class:promoted={isTagPromoted(tag)} role="button" tabindex="0" title={isAlreadyTopic(tag) ? "Already a topic" : "Promote to topic"} on:click={() => promoteWdToTopic(tag)} on:keydown={(event) => { if (event.key === 'Enter' || event.key === ' ') promoteWdToTopic(tag); }}>
                  <span class="tag-label">{tag}</span>
                  {#if countFor(fullItem.wd_tag_counts, tag)}
                      <span class="tag-count">{countFor(fullItem.wd_tag_counts, tag)}</span>
                  {/if}
                  <button class="chip-remove" type="button" title="Remove WD tag" on:click={(event) => { stopChipRemove(event); removeDraftWdTag('character', tag); }}>
                      <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                  </button>
              </span>
            {/each}
            
            {#each (draftWdGeneral || []) as tag}
              <span class="tag-chip visual" class:clickable={!isAlreadyTopic(tag)} class:promoted={isTagPromoted(tag)} role="button" tabindex="0" title={isAlreadyTopic(tag) ? "Already a topic" : "Promote to topic"} on:click={() => promoteWdToTopic(tag)} on:keydown={(event) => { if (event.key === 'Enter' || event.key === ' ') promoteWdToTopic(tag); }}>
                  <span class="tag-label">{tag}</span>
                  {#if countFor(fullItem.wd_tag_counts, tag)}
                      <span class="tag-count">{countFor(fullItem.wd_tag_counts, tag)}</span>
                  {/if}
                  <button class="chip-remove" type="button" title="Remove WD tag" on:click={(event) => { stopChipRemove(event); removeDraftWdTag('general', tag); }}>
                      <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                  </button>
              </span>
            {/each}
          </div>
          
          {#if !draftWdRating && (!draftWdCharacters || draftWdCharacters.length === 0) && (!draftWdGeneral || draftWdGeneral.length === 0)}
              <div class="value-text">No suggestions</div>
          {/if}
        </div>

        <div class="action-footer">
            <button class="tag-btn" on:click={runTagging} disabled={tagging}>
                <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" class="btn-icon">
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path>
                </svg>
                {tagging ? 'Tagging...' : 'Tag Media'}
            </button>
            
            <div class="save-group">
                {#if isDirty}
                <button class="revert-btn" on:click={revertChanges}>
                    Revert
                </button>
                {/if}
                <button class="save-btn" on:click={save} disabled={!isDirty}>
                    Save
                </button>
            </div>
        </div>
      </div>
    {/if}
  {/if}

  <MetadataActionModal
    open={renameModalOpen}
    kind="topic"
    action="rename"
    value={renameModalValue}
    bind:newValue={renameModalNewValue}
    busy={renameModalBusy}
    result={renameModalResult}
    error={renameModalError}
    onClose={closeRenameTopicModal}
    onConfirm={confirmRenameTopic}
  />
</aside>

<style>
  .inspector {
    background: var(--bg-main);
    display: flex;
    flex-direction: column;
    padding: 0;
    gap: 0;
    overflow: hidden;
    position: relative;
    height: 100%;
  }

  .inspector-header {
    display: flex;
    flex-direction: column;
    padding: 15px 15px 0 15px;
    gap: 12px;
    flex-shrink: 0;
  }

  .inspector-body {
    flex-grow: 1;
    overflow-y: auto;
    padding: 12px 15px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
  }


  .group-container {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .group-container.media-preview {
    padding: 0;
    overflow: hidden;
    position: relative;
    min-height: 200px;
    max-height: 400px;
    background: #000;
  }

  .media-preview img, .media-preview video {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .unsupported-media { min-height: 200px; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 12px; }

  .media-overlay {
      position: absolute;
      top: 10px;
      right: 10px;
      display: flex;
      gap: 5px;
      opacity: 0;
  }
  .media-preview:hover .media-overlay { opacity: 1; }

  .overlay-btn {
      width: 30px;
      height: 30px;
      padding: 0;
      background: rgba(0,0,0,0.6);
      border: 1px solid rgba(255,255,255,0.2);
      color: white;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      border-radius: 6px;
  }
  .overlay-btn:hover { background: var(--accent-primary); border-color: var(--accent-primary); }

  .group-nav {
      align-items: center;
      justify-content: space-between;
      background: rgba(0, 0, 0, 0.15) !important;
      padding: 6px 12px !important;
      margin: 0;
  }
  .group-nav button {
      width: 32px;
      height: 28px;
      padding: 0;
      display: inline-grid;
      place-items: center;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: var(--text-main);
      border-radius: 6px;
      cursor: pointer;
  }
  .group-nav button:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
      color: var(--text-bright);
  }
  .group-nav button:disabled {
      opacity: 0.3;
      cursor: not-allowed;
  }
  .group-nav .counter {
      font-size: 11px;
      font-weight: bold;
      color: #8b949e;
      display: flex;
      align-items: center;
      gap: 4px;
  }
  .group-nav .active-index {
      color: #8b949e;
      font-weight: bold;
  }

  .section-label { font-size: 11px; color: var(--text-muted); font-weight: 500; }

  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .add-topic-btn,
  .topic-confirm-btn {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    padding: 0;
    border-radius: 6px;
    border: 1px solid rgba(163, 113, 247, 0.4);
    background: rgba(163, 113, 247, 0.07);
    color: var(--accent-purple);
    font-size: 15px;
    line-height: 1;
    font-weight: 700;
    cursor: pointer;
  }

  .add-topic-btn:hover,
  .topic-confirm-btn:hover {
    border-color: var(--accent-purple);
    background: rgba(163, 113, 247, 0.12);
    color: var(--text-bright);
  }

  .topic-input-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .topic-input-wrap {
    position: relative;
  }

  .topic-input {
    flex: 1;
    min-width: 0;
    height: 26px;
    padding: 3px 8px;
    font-size: 12px;
  }

  .topic-suggestions {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 28px;
    z-index: 20;
    max-height: 180px;
    overflow-y: auto;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    background: var(--bg-panel);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
    padding: 4px 0;
  }

  .topic-suggestions.loading {
    padding: 7px 10px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .topic-suggestions button {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--text-main);
    padding: 7px 10px;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }

  .topic-suggestions button:hover,
  .topic-suggestions button.active {
    background: rgba(163, 113, 247, 0.18);
    color: var(--text-bright);
  }

  .suggestion-count {
    color: var(--text-muted);
    font-size: 11px;
  }

  .value-text {
    color: #6a737d;
    font-style: italic;
    font-weight: normal;
    font-size: 13px;
    padding: 2px 0;
  }

  .horizontal { flex-direction: row; gap: 20px; }

  /* Metadata Grid Styling */
  .metadata-grid {
    display: grid;
    grid-template-columns: 80px 1fr;
    row-gap: 6px;
    column-gap: 12px;
    align-items: center;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 10px 12px;
  }

  .grid-label {
    font-size: 10px;
    color: var(--text-muted);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    user-select: none;
  }

  .grid-value {
    display: flex;
    align-items: center;
    min-width: 0;
  }

  input.inline-input {
    width: 100%;
    height: 24px;
    padding: 2px 6px;
    margin-left: -6px; /* Offset padding exactly so text left-aligns with non-input text */
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 4px;
    color: var(--text-main);
    font-size: 12px;
    font-weight: 500;
    transition: none !important;
    box-shadow: none !important;
  }

  input.inline-input:hover {
    background: rgba(255, 255, 255, 0.03) !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
  }

  input.inline-input:focus {
    background: var(--bg-input) !important;
    border-color: var(--accent-purple) !important;
    outline: none !important;
  }

  input.inline-input.read-only-input {
    cursor: default;
    color: var(--text-muted);
  }

  input.inline-input.read-only-input:hover {
    background: transparent !important;
    border-color: transparent !important;
  }

  input.inline-input.read-only-input:focus {
    background: transparent !important;
    border-color: transparent !important;
  }

  .platform-row {
    display: flex;
    align-items: center;
  }

  .platform-text {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-main);
  }

  .source-row {
    display: flex;
    align-items: center;
    width: 100%;
    gap: 4px;
    min-width: 0;
  }

  .link-icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--accent-primary);
    opacity: 0.8;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .link-icon-btn:hover {
    opacity: 1;
    background: rgba(31, 111, 235, 0.1);
    color: var(--text-bright);
  }

  .hash-row {
    display: flex;
    align-items: center;
    width: 100%;
    gap: 6px;
    min-width: 0;
  }

  .hash-text {
    font-family: monospace;
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-grow: 1;
  }

  .icon-btn-compact {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    padding: 0;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    border-radius: 3px;
    flex-shrink: 0;
  }

  .icon-btn-compact:hover {
    background: rgba(255, 255, 255, 0.08);
    color: var(--text-bright);
  }

  .tags-list { display: flex; flex-wrap: wrap; gap: 6px; }

  .tag-chip {
      display: inline-flex;
      align-items: center;
      height: 26px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-main);
      border: 1px solid var(--border-dim);
      user-select: none;
      overflow: hidden;
      gap: 4px;
  }

  .tag-chip.clickable { cursor: pointer; }

  .tag-label {
      display: flex;
      align-items: center;
      padding: 0 0 0 8px;
      height: 100%;
  }

  /* Symmetrical even-even layout matching stats view chip counters */
  .tag-count {
      display: inline-grid;
      place-items: center;
      line-height: 1;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.08);
      border-radius: 10px;
      font-size: 10px;
      font-weight: 600;
      min-width: 18px;
      height: 18px;
      padding: 0 6px;
      margin-left: 4px;
      margin-right: 2px;
  }



  /* Slide-out removal button using clean SVG graphics */
  .chip-remove {
      display: inline-grid;
      place-items: center;
      width: 0;
      height: 24px !important;
      align-self: stretch !important;
      margin: 0 !important;
      padding: 0 !important;
      border: none !important;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      opacity: 0;
      transition: none !important;
      border-radius: 0 !important;
      box-sizing: border-box !important;
  }

  /* Slide-out rename button using clean SVG graphics */
  .chip-rename {
      display: inline-grid;
      place-items: center;
      width: 0;
      height: 24px !important;
      align-self: stretch !important;
      margin: 0 !important;
      padding: 0 !important;
      border: none !important;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      opacity: 0;
      transition: none !important;
      border-radius: 0 !important;
      box-sizing: border-box !important;
  }

  /* Svelte-safe tag chip expansion on hover */
  .tag-chip:hover .chip-remove,
  .tag-chip:focus-within .chip-remove {
      width: 24px;
      opacity: 1;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
      color: var(--text-muted);
      transition: none !important;
  }

  .tag-chip:hover .chip-rename,
  .tag-chip:focus-within .chip-rename {
      width: 24px;
      opacity: 1;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
      color: var(--text-muted);
      transition: none !important;
  }

  /* Cancel flexbox gap between adjacent action buttons to keep highlights perfectly seamless */
  .tag-chip:hover .chip-rename + .chip-remove,
  .tag-chip:focus-within .chip-rename + .chip-remove {
      margin-left: -4px !important;
  }

  /* Expand right-side margin of count when remove button is hidden, compress when shown */
  .tag-chip:hover .tag-count,
  .tag-chip:focus-within .tag-count {
      margin-right: 0;
  }

  .chip-remove:hover {
      background: rgba(248, 81, 73, 0.15) !important;
      color: var(--accent-danger) !important;
      height: 24px !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
  }

  .chip-rename:hover {
      background: rgba(255, 255, 255, 0.08) !important;
      color: var(--accent-primary) !important;
      height: 24px !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
  }

  /* Categories Hover & Color Harmonies */
  .tag-chip:hover {
      border-color: rgba(255, 255, 255, 0.2);
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-bright);
  }

  .tag-chip:hover .tag-count {
      color: var(--text-bright);
      background: rgba(255, 255, 255, 0.15);
  }

  /* Topics (Purple) */
  .tag-chip.topic {
      color: var(--accent-purple);
      border-color: rgba(163, 113, 247, 0.4);
      background: rgba(163, 113, 247, 0.07);
  }

  .tag-chip.topic:hover {
      border-color: var(--accent-purple);
      background: rgba(163, 113, 247, 0.12);
  }

  /* Ratings (Warning Orange) */
  .tag-chip.rating {
      color: var(--accent-warning);
      border-color: rgba(240, 139, 44, 0.35);
      background: rgba(240, 139, 44, 0.07);
  }

  .tag-chip.rating:hover {
      border-color: var(--accent-warning);
      background: rgba(240, 139, 44, 0.12);
  }

  /* Character Tags (Accent Blue) */
  .tag-chip.character {
      color: var(--accent-primary);
      border-color: rgba(31, 111, 235, 0.35);
      background: rgba(31, 111, 235, 0.07);
  }

  .tag-chip.character:hover {
      border-color: var(--accent-primary);
      background: rgba(31, 111, 235, 0.12);
  }

  /* Visual/General Tags (Dim Gray) */
  .tag-chip.visual {
      color: var(--text-main);
      border-color: var(--border-dim);
      background: rgba(255, 255, 255, 0.04);
  }

  .tag-chip.visual:hover {
      border-color: rgba(255, 255, 255, 0.25);
      background: rgba(255, 255, 255, 0.08);
  }

  /* ================= Promoted / Unsaved Draft Highlights ================= */
  /* Topic Draft (Purple) */
  .tag-chip.topic.promoted {
      background: var(--accent-purple) !important;
      border-color: #c9a0ff !important;
      color: #ffffff !important;
  }
  .tag-chip.topic.promoted .tag-count {
      background: #ffffff !important;
      color: var(--accent-purple) !important;
  }
  .tag-chip.topic.promoted .chip-remove {
      color: rgba(255, 255, 255, 0.7) !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }
  .tag-chip.topic.promoted .chip-remove:hover {
      background: rgba(255, 255, 255, 0.15) !important;
      color: #ffffff !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }

  .tag-chip.topic.promoted .chip-rename {
      color: rgba(255, 255, 255, 0.7) !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }
  .tag-chip.topic.promoted .chip-rename:hover {
      background: rgba(255, 255, 255, 0.15) !important;
      color: #ffffff !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }

  /* Rating Suggestion (Orange) */
  .tag-chip.rating.promoted {
      background: var(--accent-warning) !important;
      border-color: #ffb454 !important;
      color: #ffffff !important;
  }
  .tag-chip.rating.promoted .tag-count {
      background: #ffffff !important;
      color: var(--accent-warning) !important;
  }
  .tag-chip.rating.promoted .chip-remove {
      color: rgba(255, 255, 255, 0.7) !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }
  .tag-chip.rating.promoted .chip-remove:hover {
      background: rgba(255, 255, 255, 0.15) !important;
      color: #ffffff !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }

  /* Character Suggestion (Blue) */
  .tag-chip.character.promoted {
      background: var(--accent-primary) !important;
      border-color: #58a6ff !important;
      color: #ffffff !important;
  }
  .tag-chip.character.promoted .tag-count {
      background: #ffffff !important;
      color: var(--accent-primary) !important;
  }
  .tag-chip.character.promoted .chip-remove {
      color: rgba(255, 255, 255, 0.7) !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }
  .tag-chip.character.promoted .chip-remove:hover {
      background: rgba(255, 255, 255, 0.15) !important;
      color: #ffffff !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.25) !important;
      height: 24px !important;
  }

  /* Visual/General Suggestion (Dim Gray/Slate) */
  .tag-chip.visual.promoted {
      background: #8b949e !important;
      border-color: #c9d1d9 !important;
      color: #0d1117 !important;
  }
  .tag-chip.visual.promoted .tag-count {
      background: #0d1117 !important;
      color: #8b949e !important;
  }
  .tag-chip.visual.promoted .chip-remove {
      color: rgba(13, 17, 23, 0.7) !important;
      border: none !important;
      border-left: 1px solid rgba(13, 17, 23, 0.2) !important;
      height: 24px !important;
  }
  .tag-chip.visual.promoted .chip-remove:hover {
      background: rgba(13, 17, 23, 0.1) !important;
      color: #0d1117 !important;
      border: none !important;
      border-left: 1px solid rgba(13, 17, 23, 0.2) !important;
      height: 24px !important;
  }

  input { background: var(--bg-input); border: 1px solid #30363d; font-weight: 500; }

  .action-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    gap: 12px;
    margin-top: 4px;
  }

  .save-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .tag-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(163, 113, 247, 0.08);
    border: 1px solid rgba(163, 113, 247, 0.3);
    border-radius: 6px;
    color: var(--accent-purple);
    cursor: pointer;
    transition: none !important;
  }

  .tag-btn:hover:not(:disabled) {
    background: rgba(163, 113, 247, 0.15);
    border-color: var(--accent-purple);
    color: var(--text-bright);
  }

  .tag-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .revert-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--text-muted);
    cursor: pointer;
    transition: none !important;
  }

  .revert-btn:hover {
    color: var(--text-bright);
    background: rgba(255, 255, 255, 0.05);
  }

  .save-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 14px;
    font-size: 11px;
    font-weight: 700;
    background: var(--accent-purple);
    border: 1px solid var(--accent-purple);
    border-radius: 6px;
    color: #ffffff;
    cursor: pointer;
    transition: none !important;
  }

  .save-btn:hover:not(:disabled) {
    background: #b085ff;
    border-color: #b085ff;
  }

  .save-btn:disabled {
    background: rgba(255, 255, 255, 0.05);
    border-color: var(--border-dim);
    color: var(--text-muted);
    cursor: not-allowed;
    font-weight: 600;
  }

  .btn-icon {
    margin-right: 4px;
    flex-shrink: 0;
  }

  .loading-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    border-radius: 8px;
    color: var(--text-muted);
  }

  .empty-panel {
    flex-grow: 1;
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    background: var(--bg-panel);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }

  /* Sleek Horizontal Action Toolbar */
  .action-toolbar {
    flex-direction: row !important;
    gap: 6px !important;
    padding: 6px 8px !important;
    align-items: center;
  }

  .toolbar-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-grow: 1;
    height: 30px;
    padding: 0;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    color: var(--text-main);
    cursor: pointer;
    transition: none !important;
  }

  .toolbar-btn:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.2);
    color: var(--text-bright);
  }

  .toolbar-btn.delete-btn {
    color: var(--text-muted);
  }

  .toolbar-btn.delete-btn:hover {
    background: rgba(248, 81, 73, 0.15);
    border-color: rgba(248, 81, 73, 0.3);
    color: var(--accent-danger);
  }
</style>

