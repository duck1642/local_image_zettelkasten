# Orphan Data Fix Context

## Problem

Vault health found wrong-shard WD caches and thumbnails for live items, plus assets and thumbnails left behind after item deletion. The common failure was that cleanup only knew the current hash-derived path while storage-owned files could exist in another shard. Thumbnail generation could also finish after deletion and recreate a derived file.

## Ownership Invariant

The database row owns every runtime file associated with its vault and `storage_id`:

- assets: `{storage_id}.*`
- notes: `{storage_id}.md`
- WD cache: `{storage_id}.json`
- image thumbnail: `{storage_id}.jpg`
- video thumbnail: `{storage_id}_video.jpg`

Runtime publication and deletion coordinate through a process-local lifecycle lock keyed by vault root and `storage_id`.

## Deletion Flow

Deletion now prevents orphan creation:

1. Acquire the storage lifecycle lock.
2. Re-read the database row.
3. Discover canonical and wrong-shard owned files.
4. Move every existing owned file to the existing trash staging directory.
5. If staging fails, restore moved files and keep the database row.
6. Delete and commit the database row only after staging succeeds.
7. Remove staged trash files and report any final cleanup errors.

Normal, bulk, and review-replacement deletion use the same staging behavior. The previous silent post-delete sweep was removed.

## Writer Coordination

- Thumbnail generation holds the lifecycle lock through source validation and atomic publication.
- Image and video thumbnails write temporary JPEG files before replacing the final path.
- WD cache publication checks that its owning asset still exists while holding the lifecycle lock.
- Runtime note updates, repair writes, review metadata preservation, and metadata maintenance re-check ownership while holding the lock.
- Ingestion marks allowed non-media items as `thumbnail_status='skipped'` before its first commit.

## Repair Behavior

Repair remains a recovery layer:

- Thumbnail repair removes stale image and video variants even when the canonical thumbnail is fresh.
- WD repair removes only stale WD caches.
- Cleanup failures are returned in `cleanup_errors`; they are never silently discarded.
- Repair results include additive `stale_removed` and `cleanup_errors` fields.

## Regression Coverage

Backend tests cover:

- canonical and wrong-shard deletion for normal and replacement flows
- rollback when a wrong-shard file cannot be staged
- deletion waiting for in-flight thumbnail generation
- refusal to publish WD cache after owner deletion
- fresh image/video thumbnail stale-copy cleanup
- cleanup error reporting
- media-only thumbnail and WD repair filtering
- non-media ingestion thumbnail status
- workspace-wide dictionary usage and health issue counting

Full-suite results should be recorded in the commit or final implementation report after verification.
