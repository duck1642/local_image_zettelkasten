const ICONS = {
  server: [
    '<rect x="3" y="4" width="18" height="8" rx="2"></rect>',
    '<rect x="3" y="12" width="18" height="8" rx="2"></rect>',
    '<line x1="7" y1="8" x2="7.01" y2="8"></line>',
    '<line x1="7" y1="16" x2="7.01" y2="16"></line>'
  ],
  merge: [
    '<circle cx="18" cy="18" r="3"></circle>',
    '<circle cx="6" cy="6" r="3"></circle>',
    '<path d="M6 9v9a3 3 0 0 0 3 3h3"></path>',
    '<path d="M18 15V9a6 6 0 0 0-6-6H9"></path>'
  ],
  image: [
    '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>',
    '<circle cx="8.5" cy="8.5" r="1.5"></circle>',
    '<polyline points="21 15 16 10 5 21"></polyline>'
  ],
  externalLink: [
    '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>',
    '<polyline points="15 3 21 3 21 9"></polyline>',
    '<line x1="10" y1="14" x2="21" y2="3"></line>'
  ],
  chevronLeft: ['<polyline points="15 18 9 12 15 6"></polyline>'],
  chevronRight: ['<polyline points="9 18 15 12 9 6"></polyline>'],
  trash: [
    '<polyline points="3 6 5 6 21 6"></polyline>',
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>',
    '<line x1="10" y1="11" x2="10" y2="17"></line>',
    '<line x1="14" y1="11" x2="14" y2="17"></line>'
  ],
  upload: [
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>',
    '<polyline points="17 8 12 3 7 8"></polyline>',
    '<line x1="12" y1="3" x2="12" y2="15"></line>'
  ],
  checkCircle: [
    '<circle cx="12" cy="12" r="10"></circle>',
    '<path d="m9 12 2 2 4-4"></path>'
  ],
  plus: [
    '<line x1="12" y1="5" x2="12" y2="19"></line>',
    '<line x1="5" y1="12" x2="19" y2="12"></line>'
  ],
  download: [
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>',
    '<polyline points="7 10 12 15 17 10"></polyline>',
    '<line x1="12" y1="15" x2="12" y2="3"></line>'
  ]
};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

export function iconHtml(name, label = "") {
  const paths = ICONS[name] || [];
  const svg = [
    '<svg class="icon" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">',
    ...paths,
    "</svg>"
  ].join("");
  if (!label) {
    return svg;
  }
  return `${svg}<span class="icon-label">${escapeHtml(label)}</span>`;
}
