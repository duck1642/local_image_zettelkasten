import { log as uiLog } from './logger';

export interface ReviewItem {
  filename: string;
  display_name?: string;
  url: string;
  mime_type?: string;
  extension?: string;
  metadata: any;
  state?: string;
  section?: 'pending' | 'cleanup';
  last_action?: string;
  last_cleanup_error?: string;
  best_match: {
    hash: string;
    url: string;
    artist: string;
    mime_type?: string;
    extension?: string;
    width?: number;
    height?: number;
    size_bytes?: number;
    codec?: string;
    duration?: number;
    frames?: number;
    wd_tags?: string[];
    audio_present?: boolean;
  } | null;
  matches?: Array<{
    hash: string;
    url: string;
    artist: string;
    mime_type?: string;
    extension?: string;
    width?: number;
    height?: number;
    size_bytes?: number;
    codec?: string;
    duration?: number;
    frames?: number;
    wd_tags?: string[];
    audio_present?: boolean;
  }>;
}

const INCOMING_SVG_B64 = 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iNDAwIiB2aWV3Qm94PSIwIDAgNjAwIDQwMCI+CiAgPHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzBkMTExNyIgLz4KICA8cmVjdCB4PSIyMCIgeT0iMjAiIHdpZHRoPSI1NjAiIGhlaWdodD0iMzYwIiByeD0iOCIgZmlsbD0iIzFmNmZlYiIgZmlsbC1vcGFjaXR5PSIwLjEiIHN0cm9rZT0iIzFmNmZlYiIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtZGFzaGFycmF5PSI4IDQiIC8+CiAgPHRleHQgeD0iNTAlIiB5PSI0NSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiM1OGE2ZmYiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjIiIGZvbnQtd2VpZ2h0PSJib2xkIj5TQU5EQk9YIE1PREU6IElOQ09NSU5HPC90ZXh0PgogIDx0ZXh0IHg9IjUwJSIgeT0iNTUlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjYzlkMWQ5IiBmb250LWZhbWl5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiPkZpbGU6IHNhbmRib3hfaW5jb21pbmdfY29uY2VwdC5wbmc8L3RleHQ+CiAgPHRleHQgeD0iNTAlIiB5PSI6MiUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiM4Yjk0OWUiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTIiPlNpbXVsYXRlZDogSW1hZ2UgKEpQRUcpIOKAoiAxOTIweDEwODAg4oCiIDc4NCBLQjwvdGV4dD4KPC9zdmc+';

const MATCH_SVG_B64 = 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iNDAwIiB2aWV3Qm94PSIwIDAgNjAwIDQwMCI+CiAgPHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzBkMTExNyIgLz4KICA8cmVjdCB4PSIyMCIgeT0iMjAiIHdpZHRoPSI1NjAiIGhlaWdodD0iMzYwIiByeD0iOCIgZmlsbD0iI2QyOTkyMiIgZmlsbC1vcGFjaXR5PSIwLjEiIHN0cm9rZT0iI2QyOTkyMiIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtZGFzaGFycmF5PSI4IDQiIC8+CiAgPHRleHQgeD0iNTAlIiB5PSI0NSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNmMDg4M2MiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjIiIGZvbnQtd2VpZ2h0PSJib2xkIj5TQU5EQk9YIE1PREU6IFZBVUxUIE1BVENIIDE8L3RleHQ+CiAgPHRleHQgeD0iNTAlIiB5PSI1OSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNjOWQxZDkiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiPkZpbGU6IHZhdWx0X21hdGNoaW5nX2NvcHkucG5nPC90ZXh0PgogIDx0ZXh0IHg9IjUwJSIgeT0iNjIlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOGI5NDllIiBmb250LWZhbWl5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTIiPlNpbXVsYXRlZDogSW1hZ2UgKEpQRUcpIOKAoiAxMjgweDcyMCDigKIgMzEyIEtCPC90ZXh0Pgo8L3N2Zz4=';

const ALT_SVG_B64 = 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iNDAwIiB2aWV3Qm94PSIwIDAgNjAwIDQwMCI+CiAgPHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzBkMTExNyIgLz4KICA8cmVjdCB4PSIyMCIgeT0iMjAiIHdpZHRoPSI1NjAiIGhlaWdodD0iMzYwIiByeD0iOCIgZmlsbD0iI2Y4NTE0OSIgZmlsbC1vcGFjaXR5PSIwLjEiIHN0cm9rZT0iI2Y4NTE0OSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtZGFzaGFycmF5PSI4IDQiIC8+CiAgPHRleHQgeD0iNTAlIiB5PSI0NSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNmODUxNDkiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjIiIGZvbnQtd2VpZ2h0PSJib2xkIj5TQU5EQk9YIE1PREU6IFZBVUxUIE1BVENIIDI8L3RleHQ+CiAgPHRleHQgeD0iNTAlIiB5PSI1OSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNjOWQxZDkiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiPkZpbGU6IGFsdGVybmF0ZV9jcmltc29uX2NvcHkucG5nPC90ZXh0PgogIDx0ZXh0IHg9IjUwJSIgeT0iNjIlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOGI5NDllIiBmb250LWZhbWl5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTIiPlNpbXVsYXRlZDogSW1hZ2UgKFBORykg4oCiIDgwMHg2MDAg4oCiIDEuMiBNQjwvdGV4dD4KPC9zdmc+';

const CLEANUP_SVG_B64 = 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MDAiIGhlaWdodD0iNDAwIiB2aWV3Qm94PSIwIDAgNjAwIDQwMCI+CiAgPHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzBkMTExNyIgLz4KICA8cmVjdCB4PSIyMCIgeT0iMjAiIHdpZHRoPSI1NjAiIGhlaWdodD0iMzYwIiByeD0iOCIgZmlsbD0iI2Y4NTE0OSIgZmlsbC1vcGFjaXR5PSIwLjEiIHN0cm9rZT0iI2Y4NTE0OSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtZGFzaGFycmF5PSI4IDQiIC8+CiAgPHRleHQgeD0iNTAlIiB5PSI0NSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNmODUxNDkiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjIiIGZvbnQtd2VpZ2h0PSJib2xkIj5TQU5EQk9YIE1PREU6IENMRUFOVVAgUkVRVUlSRUQ8L3RleHQ+CiAgPHRleHQgeD0iNTAlIiB5PSI1NSUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNjOWQxZDkiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiPkZpbGU6IHNhbmRib3hfY2xlYW51cF9lcnJvci5wbmc8L3RleHQ+CiAgPHRleHQgeD0iNTAlIiB5PSI2MiUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiM4Yjk0OWUiIGZvbnQtZmFtaWx5PSJzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTIiPlNpbXVsYXRlZDogT3JwaGFuIHJldmlldyBhc3NldCBsZWZ0IGJlaGluZCBkdXJpbmcgZGVsZXRpb24gZmFpbHVyZTwvdGV4dD4KPC9zdmc+';

export function getMockSandboxItems(): ReviewItem[] {
  return [
    {
      filename: 'sandbox_incoming_concept.png',
      display_name: 'sandbox_incoming_concept.png',
      url: `data:image/svg+xml;base64,${INCOMING_SVG_B64}`,
      mime_type: 'image/png',
      extension: '.png',
      metadata: {
        original_name: 'sandbox_incoming_concept.png',
        best_match: 'd3b07384d113edec49eaa6238ad5ff00',
        matches: [
          'd3b07384d113edec49eaa6238ad5ff00',
          'ae88862f91a27e77a288fb82de711200'
        ],
        width: 1920,
        height: 1080,
        size_bytes: 802816, // ~784 KB
        wd_tags: ['illustration', 'sci-fi', 'spaceship', 'concept_art', 'original_character']
      },
      state: 'pending decision',
      section: 'pending',
      best_match: {
        hash: 'd3b07384d113edec49eaa6238ad5ff00',
        url: `data:image/svg+xml;base64,${MATCH_SVG_B64}`,
        artist: 'Sandbox Artist A (Primary)',
        mime_type: 'image/png',
        extension: '.png',
        width: 1280,
        height: 720,
        size_bytes: 319488, // ~312 KB
        wd_tags: ['illustration', 'spaceship', 'sky', 'clouds']
      },
      matches: [
        {
          hash: 'd3b07384d113edec49eaa6238ad5ff00',
          url: `data:image/svg+xml;base64,${MATCH_SVG_B64}`,
          artist: 'Sandbox Artist A (Primary Copy)',
          mime_type: 'image/png',
          extension: '.png',
          width: 1280,
          height: 720,
          size_bytes: 319488,
          wd_tags: ['illustration', 'spaceship', 'sky', 'clouds']
        },
        {
          hash: 'ae88862f91a27e77a288fb82de711200',
          url: `data:image/svg+xml;base64,${ALT_SVG_B64}`,
          artist: 'Sandbox Artist B (Alternate Copy)',
          mime_type: 'image/png',
          extension: '.png',
          width: 2560,
          height: 1440,
          size_bytes: 1258291, // ~1.2 MB
          wd_tags: ['illustration', 'sci-fi', 'spaceship', 'cyberpunk', 'cityscape']
        }
      ]
    },
    {
      filename: 'sandbox_cleanup_error.png',
      display_name: 'sandbox_cleanup_error.png',
      url: `data:image/svg+xml;base64,${CLEANUP_SVG_B64}`,
      mime_type: 'image/png',
      extension: '.png',
      metadata: {
        original_name: 'sandbox_cleanup_error.png',
        last_action: 'delete',
        last_cleanup_error: 'OSError: [WinError 32] The process cannot access the file because it is being used by another process: \'C:\\\\Users\\\\Bilgisayar\\\\AppData\\\\Local\\\\Temp\\\\sandbox_cleanup_error.png\''
      },
      state: 'pending_cleanup',
      section: 'cleanup',
      best_match: null,
      matches: []
    }
  ];
}

export interface SandboxActionResult {
  nextItems: ReviewItem[];
  isSandbox: boolean;
}

export async function simulateSandboxAction(
  action: 'keep' | 'delete' | 'variant' | 'replace' | 'retryCleanup',
  filename: string,
  currentItems: ReviewItem[],
  targetHash?: string
): Promise<SandboxActionResult> {
  // Simulate native application network latency
  await new Promise((resolve) => setTimeout(resolve, 400));

  const targetItem = currentItems.find((item) => item.filename === filename);
  const displayName = targetItem?.display_name || filename;

  if (action === 'retryCleanup') {
    uiLog('INFO', 'Sandbox cleanup retried successfully (SIMULATED)', {
      cleaned: 1,
      failed: 0,
      cleaned_orphans: 0,
      failed_orphans: 0
    });
    // Remove the cleanup item
    const nextItems = currentItems.filter((item) => item.filename !== filename);
    return {
      nextItems,
      isSandbox: nextItems.length > 0
    };
  }

  const activeReplaceHash = targetHash || targetItem?.best_match?.hash || '';

  uiLog('INFO', `Review sandbox action "${action}" succeeded (SIMULATED)`, {
    action,
    filename,
    display_name: displayName,
    target_hash: activeReplaceHash,
    message: action === 'replace'
      ? `[SANDBOX] Ingested staged file to replace specific duplicate copy: ${activeReplaceHash.slice(0, 10)}...`
      : `[SANDBOX] Simulating successful '${action}' operation.`
  });

  // Filter out the completed item from sandbox
  const nextItems = currentItems.filter((item) => item.filename !== filename);
  return {
    nextItems,
    isSandbox: nextItems.length > 0
  };
}
