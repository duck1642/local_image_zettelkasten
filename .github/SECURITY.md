# Security Policy

LMZ is a local-first desktop application. It stores media metadata, credentials, and application data on the user's machine and does not provide a hosted service.

## Reporting a Vulnerability

Please do not disclose security vulnerabilities in a public issue.

Use GitHub's private vulnerability reporting for this repository when it is available. If it is unavailable, open a minimal issue without sensitive details and request a private follow-up through GitHub.

Include, when safe to share:

- the affected version or commit;
- the operating system and relevant environment details;
- reproducible steps;
- the potential impact; and
- sanitized logs or screenshots.

Never include media files, vault data, credentials, cookies, API keys, tokens, or unredacted local paths. In particular, remove files from `%USERPROFILE%\.lmz\app\secrets\auth\` before sharing diagnostics.

Security fixes are considered for the latest version on the default branch. Older versions may not receive fixes.
