<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { log as uiLog } from './logger';
  import { runtimeSessionKey } from './runtimeStore';
  import './stats/stats.css';
  import ArtistMergeModal from './stats/ArtistMergeModal.svelte';
  import ArtistStatsPanel from './stats/ArtistStatsPanel.svelte';
  import FacetStatsPanel from './stats/FacetStatsPanel.svelte';
  import MetadataActionModal from './stats/MetadataActionModal.svelte';
  import StatsControls from './stats/StatsControls.svelte';
  import StatsFilterBar from './stats/StatsFilterBar.svelte';
  import { IconClose, IconPlus } from './icons';
  import {
    addArtistAlias,
    addArtistLink,
    createTopic,
    deleteArtistAlias,
    deleteArtistLink,
    deleteTopic,
    deleteWdTag,
    fetchArtistDetail,
    fetchArtistPlaceholders,
    fetchArtists,
    fetchFacets,
    fetchMergeCandidates,
    fetchPlatformFacets,
    fetchPlatformOptions,
    mergeArtists,
    mergeTopic,
    previewArtistMerge,
    renameTopic,
    renameWdTag,
    saveArtistDetail
  } from './stats/statsApi';
  import {
    filterArtistsByLetter,
    filterFacetsByLetter,
    isPlaceholderArtist,
    isSelectableFacet,
    normalizeArtistListWidth,
    sortArtistItems,
    sortFacetItems
  } from './stats/statsUtils';
  import {
    letterFilters,
    statsKinds,
    type ArtistDetail,
    type ArtistDraft,
    type ArtistLinkDraft,
    type ArtistListItem,
    type ArtistMergePreview,
    type FacetItem,
    type FacetKind,
    type FilterVaultPayload,
    type MetadataActionKind,
    type PlatformListItem,
    type StatsScopeMode,
    type StatsSortMode
  } from './stats/types';

  const dispatch = createEventDispatcher<{ filterVault: FilterVaultPayload }>();

  let activeKind: FacetKind = 'wd_tag';
  let sortMode: StatsSortMode = 'popularity';
  let scopeMode: StatsScopeMode = 'used';
  let letterFilter = 'all';
  let searchText = '';
  let items: FacetItem[] = [];
  let artists: ArtistListItem[] = [];
  let placeholderArtists: FacetItem[] = [];
  let selectedArtistId: number | null = null;
  let selectedArtist: ArtistDetail | null = null;
  let artistDraft: ArtistDraft = { name: '', kind: 'artist', notes: '' };
  let newAlias = '';
  let newLink: ArtistLinkDraft = { platform: '', url: '', handle: '' };
  let platformOptions: PlatformListItem[] = [];
  let linkPlatformOptions: string[] = [];
  let loading = false;
  let artistSaving = false;
  let error = '';
  let debounceTimer: number | null = null;
  let requestSeq = 0;
  let artistListWidth = 320;
  let artistResizeStartX = 0;
  let artistResizeStartWidth = 320;
  let isResizingArtistList = false;
  let mergeOpen = false;
  let mergeSearch = '';
  let mergeCandidates: ArtistListItem[] = [];
  let selectedMergeSourceIds: number[] = [];
  let mergePreview: ArtistMergePreview | null = null;
  let mergeBusy = false;
  let mergeError = '';
  let mergeSearchTimer: number | null = null;
  let selectedTopics: string[] = [];
  let selectedWdTags: string[] = [];
  let metadataActionOpen = false;
  let metadataActionKind: FacetKind = 'topic';
  let metadataAction: MetadataActionKind = 'rename';
  let metadataActionValue = '';
  let metadataActionNewValue = '';
  let metadataActionTargetValue = '';
  let metadataActionTagType = '';
  let metadataActionBusy = false;
  let metadataActionResult = '';
  let metadataActionError = '';
  let topicCreateOpen = false;
  let topicCreateValue = '';
  let topicCreateBusy = false;
  let topicCreateError = '';
  let currentRuntimeSessionKey = '';

  $: showLetterFilter = activeKind === 'artist' || activeKind === 'topic' || activeKind === 'wd_tag';
  $: showScopeFilter = activeKind === 'artist' || activeKind === 'platform' || activeKind === 'topic' || activeKind === 'wd_tag';
  $: visibleArtists = filterArtistsByLetter(artists, showLetterFilter, letterFilter);
  $: visiblePlaceholderArtists = filterFacetsByLetter(placeholderArtists, showLetterFilter, letterFilter);
  $: visibleItems = filterFacetsByLetter(items, showLetterFilter, letterFilter);
  $: selectedTopicCount = selectedTopics.length;
  $: selectedWdTagCount = selectedWdTags.length;
  $: selectedFacetCount = selectedTopicCount + selectedWdTagCount;
  $: {
    const values = new Set<string>();
    for (const platform of platformOptions) {
      if (platform.display_name) values.add(platform.display_name);
    }
    for (const link of selectedArtist?.links || []) {
      if (link.platform) values.add(link.platform);
    }
    if (newLink.platform) values.add(newLink.platform);
    linkPlatformOptions = [...values];
  }
  $: if ($runtimeSessionKey) {
    if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) {
      resetForRuntimeSwitch();
    }
    currentRuntimeSessionKey = $runtimeSessionKey;
  }

  async function loadPlatformOptions() {
    try {
      platformOptions = await fetchPlatformOptions();
    } catch (err) {
      uiLog('ERROR', 'Failed to load platform options', { error: String(err) });
    }
  }

  async function loadArtistDetail(id: number, seq = requestSeq) {
    const detail = await fetchArtistDetail(id);
    if (seq !== requestSeq) return;
    selectedArtist = detail;
    artistDraft = {
      name: detail.name || '',
      kind: detail.kind || 'artist',
      notes: detail.notes || ''
    };
  }

  async function loadFacets() {
    const seq = ++requestSeq;
    loading = true;
    error = '';
    try {
      if (activeKind === 'artist') {
        const [artistData, facetData] = await Promise.all([
          fetchArtists(searchText, scopeMode),
          fetchArtistPlaceholders(searchText)
        ]);
        if (seq !== requestSeq) return;
        artists = sortArtistItems(artistData.filter((artist) => !isPlaceholderArtist(artist.name)), sortMode);
        placeholderArtists = sortFacetItems(facetData.filter((item) => isPlaceholderArtist(item.value)), sortMode);
        if (!selectedArtistId || !artists.some((artist) => artist.id === selectedArtistId)) {
          selectedArtistId = artists[0]?.id ?? null;
        }
        if (selectedArtistId) await loadArtistDetail(selectedArtistId, seq);
        else selectedArtist = null;
        return;
      }
      if (activeKind === 'platform') {
        const nextItems = await fetchPlatformFacets(searchText, scopeMode);
        if (seq !== requestSeq) return;
        items = sortFacetItems(nextItems, sortMode);
        return;
      }
      const nextItems = await fetchFacets(activeKind, searchText, scopeMode);
      if (seq !== requestSeq) return;
      items = sortFacetItems(nextItems, sortMode);
    } catch (err) {
      if (seq !== requestSeq) return;
      error = 'Failed to load stats';
      uiLog('ERROR', 'Failed to load stats', { error: String(err), kind: activeKind });
    } finally {
      if (seq === requestSeq) loading = false;
    }
  }

  function setKind(kind: FacetKind) {
    activeKind = kind;
    letterFilter = 'all';
    error = '';
    loadFacets();
  }

  function setSortMode(mode: StatsSortMode) {
    sortMode = mode;
    if (activeKind === 'artist') {
      artists = sortArtistItems(artists, sortMode);
      placeholderArtists = sortFacetItems(placeholderArtists, sortMode);
      return;
    }
    items = sortFacetItems(items, sortMode);
  }

  function setScopeMode(mode: StatsScopeMode) {
    scopeMode = mode;
    loadFacets();
  }

  function setLetterFilter(value: string) {
    letterFilter = value;
  }


  function toggleFacetSelection(kind: FacetKind, value: string) {
    if (!isSelectableFacet(kind)) return;
    if (kind === 'topic') {
      selectedTopics = selectedTopics.includes(value)
        ? selectedTopics.filter((item) => item !== value)
        : [...selectedTopics, value];
      return;
    }
    selectedWdTags = selectedWdTags.includes(value)
      ? selectedWdTags.filter((item) => item !== value)
      : [...selectedWdTags, value];
  }

  function openMetadataAction(kind: FacetKind, action: MetadataActionKind, value: string) {
    metadataActionOpen = true;
    metadataActionKind = kind;
    metadataAction = action;
    metadataActionValue = value;
    metadataActionNewValue = action === 'rename' ? value : '';
    metadataActionTargetValue = '';
    metadataActionTagType = '';
    metadataActionResult = '';
    metadataActionError = '';
  }

  function closeMetadataAction() {
    if (metadataActionBusy) return;
    metadataActionOpen = false;
    metadataActionValue = '';
    metadataActionNewValue = '';
    metadataActionTargetValue = '';
    metadataActionTagType = '';
    metadataActionResult = '';
    metadataActionError = '';
  }

  function replaceSelectedValue(values: string[], oldValue: string, newValue: string) {
    const next = values.map((value) => value === oldValue ? newValue : value);
    return [...new Set(next.filter(Boolean))];
  }

  function emitSelectionUpdateIfNeeded() {
    if (selectedTopics.length === 0 && selectedWdTags.length === 0) return;
    dispatch('filterVault', { topics: selectedTopics, wd_tags: selectedWdTags });
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

  function openTopicCreate() {
    topicCreateOpen = true;
    topicCreateValue = '';
    topicCreateError = '';
  }

  function closeTopicCreate() {
    if (topicCreateBusy) return;
    topicCreateOpen = false;
    topicCreateValue = '';
    topicCreateError = '';
  }

  async function confirmTopicCreate() {
    if (!topicCreateValue.trim() || topicCreateBusy) return;
    const label = normalizeTopicLabel(topicCreateValue);
    topicCreateBusy = true;
    topicCreateError = '';
    try {
      const payload = await createTopic(label);
      scopeMode = 'all';
      letterFilter = 'all';
      await loadFacets();
      topicCreateOpen = false;
      topicCreateValue = '';
      topicCreateError = '';
      uiLog('INFO', 'Topic created from stats', { label: payload.label || label });
    } catch (err) {
      topicCreateError = `Failed to create topic: ${String(err)}`;
      uiLog('ERROR', 'Failed to create topic from stats', { label, error: String(err) });
    } finally {
      topicCreateBusy = false;
    }
  }

  function handleTopicCreateKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      confirmTopicCreate();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      closeTopicCreate();
    }
  }

  async function confirmMetadataAction() {
    if (!metadataActionValue) return;
    metadataActionBusy = true;
    metadataActionResult = '';
    metadataActionError = '';
    try {
      let payload: any;
      if (metadataActionKind === 'topic' && metadataAction === 'rename') {
        payload = await renameTopic(metadataActionValue, metadataActionNewValue);
        selectedTopics = replaceSelectedValue(selectedTopics, metadataActionValue, String(payload.new_label || metadataActionNewValue.trim()));
      } else if (metadataActionKind === 'topic' && metadataAction === 'merge') {
        payload = await mergeTopic(metadataActionValue, metadataActionTargetValue);
        selectedTopics = replaceSelectedValue(selectedTopics, metadataActionValue, String(payload.target_label || metadataActionTargetValue.trim()));
      } else if (metadataActionKind === 'topic') {
        payload = await deleteTopic(metadataActionValue);
        selectedTopics = selectedTopics.filter((topic) => topic !== metadataActionValue);
      } else if (metadataAction === 'rename') {
        payload = await renameWdTag(metadataActionValue, metadataActionNewValue, metadataActionTagType);
        selectedWdTags = replaceSelectedValue(selectedWdTags, metadataActionValue, String(payload.new_tag || metadataActionNewValue.trim()));
      } else {
        payload = await deleteWdTag(metadataActionValue, metadataActionTagType);
        selectedWdTags = selectedWdTags.filter((tag) => tag !== metadataActionValue);
      }
      const vaultCount = Array.isArray(payload?.vaults_touched) ? payload.vaults_touched.length : 0;
      metadataActionResult = `Updated ${payload.notes_rewritten || 0} notes across ${vaultCount} vaults.`;
      await loadFacets();
      emitSelectionUpdateIfNeeded();
      uiLog('INFO', 'Metadata maintenance action completed', {
        kind: metadataActionKind,
        action: metadataAction,
        value: metadataActionValue,
        notes: payload.notes_rewritten
      });
    } catch (err) {
      metadataActionError = `Failed to update metadata: ${String(err)}`;
      uiLog('ERROR', 'Failed metadata maintenance action', {
        kind: metadataActionKind,
        action: metadataAction,
        value: metadataActionValue,
        error: String(err)
      });
    } finally {
      metadataActionBusy = false;
    }
  }

  function clearFacetSelection() {
    selectedTopics = [];
    selectedWdTags = [];
  }

  function resetForRuntimeSwitch() {
    requestSeq += 1;
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    closeMergeModal();
    closeMetadataAction();
    searchText = '';
    letterFilter = 'all';
    items = [];
    artists = [];
    placeholderArtists = [];
    selectedArtistId = null;
    selectedArtist = null;
    artistDraft = { name: '', kind: 'artist', notes: '' };
    newAlias = '';
    newLink = { platform: '', url: '', handle: '' };
    platformOptions = [];
    selectedTopics = [];
    selectedWdTags = [];
    closeTopicCreate();
    error = '';
    loading = false;
    loadPlatformOptions();
    loadFacets();
  }

  function filterVaultFromSelection() {
    if (selectedFacetCount <= 0) return;
    dispatch('filterVault', { topics: selectedTopics, wd_tags: selectedWdTags });
    uiLog('INFO', 'Stats filter sent to vault', { topics: selectedTopicCount, wd_tags: selectedWdTagCount });
    clearFacetSelection();
  }

  async function selectArtist(id: number) {
    selectedArtistId = id;
    loading = true;
    error = '';
    const seq = ++requestSeq;
    try {
      await loadArtistDetail(id, seq);
    } catch (err) {
      if (seq !== requestSeq) return;
      error = 'Failed to load artist';
      uiLog('ERROR', 'Failed to load artist detail', { id, error: String(err) });
    } finally {
      if (seq === requestSeq) loading = false;
    }
  }

  function handleSearchInput() {
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadFacets, 200);
  }

  async function loadMergeCandidates() {
    if (!selectedArtist) return;
    mergeError = '';
    try {
      mergeCandidates = await fetchMergeCandidates(mergeSearch, selectedArtist.id);
    } catch (err) {
      mergeError = `Failed to load merge candidates: ${String(err)}`;
      uiLog('ERROR', 'Failed to load merge candidates', { error: String(err) });
    }
  }

  async function refreshMergePreview() {
    if (!selectedArtist || selectedMergeSourceIds.length === 0) {
      mergePreview = null;
      return;
    }
    mergeError = '';
    try {
      mergePreview = await previewArtistMerge(selectedArtist.id, selectedMergeSourceIds);
    } catch (err) {
      mergePreview = null;
      mergeError = `Failed to preview merge: ${String(err)}`;
      uiLog('ERROR', 'Failed to preview artist merge', { error: String(err) });
    }
  }

  function openMergeModal() {
    if (!selectedArtist) return;
    mergeOpen = true;
    mergeSearch = '';
    selectedMergeSourceIds = [];
    mergePreview = null;
    mergeError = '';
    loadMergeCandidates();
  }

  function closeMergeModal() {
    mergeOpen = false;
    mergeSearch = '';
    mergeCandidates = [];
    selectedMergeSourceIds = [];
    mergePreview = null;
    mergeError = '';
    if (mergeSearchTimer !== null) {
      clearTimeout(mergeSearchTimer);
      mergeSearchTimer = null;
    }
  }

  function handleMergeSearchInput() {
    if (mergeSearchTimer !== null) clearTimeout(mergeSearchTimer);
    mergeSearchTimer = setTimeout(loadMergeCandidates, 200);
  }

  async function toggleMergeSource(id: number) {
    selectedMergeSourceIds = selectedMergeSourceIds.includes(id)
      ? selectedMergeSourceIds.filter((sourceId) => sourceId !== id)
      : [...selectedMergeSourceIds, id];
    await refreshMergePreview();
  }

  function startArtistResize(event: PointerEvent) {
    event.preventDefault();
    isResizingArtistList = true;
    artistResizeStartX = event.clientX;
    artistResizeStartWidth = artistListWidth;
    document.body.classList.add('artist-list-resizing');
    window.addEventListener('pointermove', handleArtistResize);
    window.addEventListener('pointerup', stopArtistResize);
    window.addEventListener('pointercancel', stopArtistResize);
  }

  function handleArtistResize(event: PointerEvent) {
    if (!isResizingArtistList) return;
    artistListWidth = normalizeArtistListWidth(artistResizeStartWidth + event.clientX - artistResizeStartX);
  }

  function stopArtistResize() {
    if (!isResizingArtistList) return;
    isResizingArtistList = false;
    document.body.classList.remove('artist-list-resizing');
    window.removeEventListener('pointermove', handleArtistResize);
    window.removeEventListener('pointerup', stopArtistResize);
    window.removeEventListener('pointercancel', stopArtistResize);
  }

  function handleArtistResizeKeydown(event: KeyboardEvent) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const delta = event.key === 'ArrowLeft' ? -20 : 20;
    artistListWidth = normalizeArtistListWidth(artistListWidth + delta);
  }

  async function saveArtist() {
    if (!selectedArtist) return;
    artistSaving = true;
    error = '';
    try {
      const updated = await saveArtistDetail(selectedArtist.id, artistDraft);
      selectedArtist = updated;
      await loadFacets();
      uiLog('INFO', 'Artist updated', { id: updated.id, name: updated.name });
    } catch (err) {
      error = `Failed to save artist: ${String(err)}`;
      uiLog('ERROR', 'Failed to save artist', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function addAlias() {
    if (!selectedArtist || !newAlias.trim()) return;
    artistSaving = true;
    error = '';
    try {
      await addArtistAlias(selectedArtist.id, newAlias);
      newAlias = '';
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to add alias: ${String(err)}`;
      uiLog('ERROR', 'Failed to add artist alias', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function deleteAlias(aliasId: number) {
    if (!selectedArtist) return;
    artistSaving = true;
    error = '';
    try {
      await deleteArtistAlias(selectedArtist.id, aliasId);
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to delete alias: ${String(err)}`;
      uiLog('ERROR', 'Failed to delete artist alias', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function confirmMerge() {
    if (!selectedArtist || selectedMergeSourceIds.length === 0) return;
    const sourceCount = selectedMergeSourceIds.length;
    mergeBusy = true;
    mergeError = '';
    try {
      const merged = await mergeArtists(selectedArtist.id, selectedMergeSourceIds);
      if (merged.target_detail) {
        selectedArtist = merged.target_detail;
        artistDraft = {
          name: selectedArtist.name,
          kind: selectedArtist.kind,
          notes: selectedArtist.notes
        };
      } else {
        await loadArtistDetail(selectedArtist.id);
      }
      await loadFacets();
      closeMergeModal();
      uiLog('INFO', 'Artists merged', { target_id: selectedArtistId, sources: sourceCount });
    } catch (err) {
      mergeError = `Failed to merge artists: ${String(err)}`;
      uiLog('ERROR', 'Failed to merge artists', { error: String(err) });
    } finally {
      mergeBusy = false;
    }
  }

  async function addLink() {
    if (!selectedArtist || !newLink.platform.trim() || !newLink.url.trim()) return;
    artistSaving = true;
    error = '';
    try {
      await addArtistLink(selectedArtist.id, newLink);
      newLink = { platform: '', url: '', handle: '' };
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to add link: ${String(err)}`;
      uiLog('ERROR', 'Failed to add artist link', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function deleteLink(linkId: number) {
    if (!selectedArtist) return;
    artistSaving = true;
    error = '';
    try {
      await deleteArtistLink(selectedArtist.id, linkId);
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to delete link: ${String(err)}`;
      uiLog('ERROR', 'Failed to delete artist link', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'stats') return;
    uiLog('INFO', 'Stats view refresh requested', { kind: activeKind });
    loadFacets();
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadFacets();
    loadPlatformOptions();
    return () => {
      window.removeEventListener('lmz:refresh', handleGlobalRefresh);
      if (debounceTimer !== null) clearTimeout(debounceTimer);
      if (mergeSearchTimer !== null) clearTimeout(mergeSearchTimer);
      stopArtistResize();
    };
  });
</script>

<div class="stats-container">
  <div class="stats-header">
    <div class="header-left">
      <h3>Vault Stats</h3>
      <span class="value-count">{activeKind === 'artist' ? visibleArtists.length + visiblePlaceholderArtists.length : visibleItems.length} values</span>
    </div>
    <div class="kind-tabs">
      {#each statsKinds as kind}
        <button type="button" class:active={activeKind === kind.value} on:click={() => setKind(kind.value)}>
          {kind.label}
        </button>
      {/each}
    </div>
  </div>

  <StatsControls
    {sortMode}
    {scopeMode}
    bind:letterFilter
    bind:searchText
    {letterFilters}
    {showLetterFilter}
    {showScopeFilter}
    onSort={setSortMode}
    onScope={setScopeMode}
    onLetter={setLetterFilter}
    onSearchInput={handleSearchInput}
  />

  {#if activeKind === 'artist'}
    <ArtistStatsPanel
      {visibleArtists}
      {visiblePlaceholderArtists}
      bind:selectedArtistId
      bind:selectedArtist
      bind:artistDraft
      bind:newAlias
      bind:newLink
      {linkPlatformOptions}
      {loading}
      {error}
      {artistSaving}
      {artistListWidth}
      {isResizingArtistList}
      onSelectArtist={selectArtist}
      onStartResize={startArtistResize}
      onResizeKeydown={handleArtistResizeKeydown}
      onSaveArtist={saveArtist}
      onAddAlias={addAlias}
      onDeleteAlias={deleteAlias}
      onAddLink={addLink}
      onDeleteLink={deleteLink}
      onOpenMerge={openMergeModal}
    />
  {:else}
    {#if activeKind === 'topic'}
      <div class="topic-create-bar">
        {#if topicCreateOpen}
          <input
            type="text"
            bind:value={topicCreateValue}
            placeholder="Topic"
            disabled={topicCreateBusy}
            on:keydown={handleTopicCreateKeydown}
          />
          <button type="button" title="Create topic" aria-label="Create topic" disabled={topicCreateBusy || !topicCreateValue.trim()} on:click={confirmTopicCreate}>
            <IconPlus size={12} />
          </button>
          <button type="button" title="Cancel" aria-label="Cancel" disabled={topicCreateBusy} on:click={closeTopicCreate}>
            <IconClose size={12} />
          </button>
          {#if topicCreateError}
            <span class="topic-create-error">{topicCreateError}</span>
          {/if}
        {:else}
          <button class="topic-create-toggle" type="button" title="Create topic" aria-label="Create topic" on:click={openTopicCreate}>
            <IconPlus size={12} />
          </button>
        {/if}
      </div>
    {/if}
    <FacetStatsPanel
      {activeKind}
      {visibleItems}
      {loading}
      {error}
      {selectedTopics}
      {selectedWdTags}
      onToggleFacet={toggleFacetSelection}
      onOpenMetadataAction={openMetadataAction}
    />
  {/if}
</div>

<StatsFilterBar
  {selectedFacetCount}
  {selectedTopicCount}
  {selectedWdTagCount}
  onClear={clearFacetSelection}
  onFilterVault={filterVaultFromSelection}
/>

<MetadataActionModal
  open={metadataActionOpen}
  kind={metadataActionKind}
  action={metadataAction}
  value={metadataActionValue}
  bind:newValue={metadataActionNewValue}
  bind:targetValue={metadataActionTargetValue}
  bind:tagType={metadataActionTagType}
  busy={metadataActionBusy}
  result={metadataActionResult}
  error={metadataActionError}
  onClose={closeMetadataAction}
  onConfirm={confirmMetadataAction}
/>

<ArtistMergeModal
  open={mergeOpen}
  {selectedArtist}
  bind:mergeSearch
  {mergeCandidates}
  {selectedMergeSourceIds}
  {mergePreview}
  {mergeBusy}
  {mergeError}
  onSearchInput={handleMergeSearchInput}
  onToggleSource={toggleMergeSource}
  onConfirm={confirmMerge}
  onClose={closeMergeModal}
/>
