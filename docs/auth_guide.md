# Downloader Authentication Guide

This document describes how to configure authentication for external media extractors (such as `gallery-dl` and `yt-dlp`) used by Local Media Zettelkasten (LMZ).

---

## Overview

LMZ stores all downloader credentials in an app-global directory. By default, this path is:
`.lmz/app/secrets/auth/`

You can override this location by setting the `LMZ_AUTH_ROOT` environment variable.

Credentials must be placed in platform-specific subfolders:
- `x/cookies.txt` (X / Twitter)
- `instagram/cookies.txt` (Instagram)
- `pinterest/cookies.txt` (Pinterest)
- `youtube/cookies.txt` (YouTube)
- `pixiv/refresh_token.txt` (Pixiv OAuth - *Recommended*)
- `pixiv/cookies.txt` (Pixiv Cookies - *Fallback*)

### Local API Key (`.lmz/app/secrets/.api_key`)
In the root of the `.lmz/app/secrets/` directory, you will see a `.api_key` file:
* **Do not delete this file.**
* This is an automatically generated key used by the **LMZ browser extension** and the **Tauri frontend** to authenticate requests with the local FastAPI backend.
* **To Rotate/Recreate the Key:** If your key is compromised or you want to rotate it, simply delete the `.api_key` file. The backend will automatically generate a new one the next time it starts up (remember to copy the new key to your browser extension settings).

---

## 1. Cookie-Based Authentication (All Platforms)

To authenticate with cookies, you need to export your active login session cookies from your web browser in the standard **Netscape HTTP Cookie File** format.

### How to extract cookies easily:
1. Install a trusted cookie exporter browser extension (such as **"Get cookies.txt LOCALLY"** on Chrome, Brave, Edge, or Firefox).
2. Go to the platform's website (e.g. `x.com`, `instagram.com`, `pinterest.com`, `youtube.com`, or `pixiv.net`) and make sure you are logged in.
3. Click the cookie exporter extension icon and choose to download/export the cookies for the current domain.
4. Rename the exported file to `cookies.txt`.
5. Copy/paste this `cookies.txt` file into the corresponding platform folder under `.lmz/app/secrets/auth/`.

For example, your X cookies should end up at:
`.lmz/app/secrets/auth/x/cookies.txt`

---

## 2. Pixiv Authentication Options

Pixiv supports two authentication methods. OAuth is the recommended way, but cookies are supported as a fallback.

### Method A: OAuth Refresh Token (Recommended)
This uses the official Pixiv Android client API, which bypasses web rate limits and supports high-resolution downloads.

1. Open your terminal and navigate to the `backend/` folder:
   ```powershell
   cd backend
   python scripts/auth_pixiv.py
   ```
2. The script will print a unique login URL. **Copy and open this URL in your web browser.**
3. Log in to your Pixiv account.
4. After logging in, the browser will attempt to redirect to a mobile app scheme and fail, resulting in a **blank/white screen** or a protocol warning page. **This is expected behavior.**
5. Press `F12` to open Developer Tools, go to the **Console** or **Network** tab, and look for a warning or redirect URL containing the `code=` parameter (e.g., `https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback?code=XYZ...`).
6. Copy that entire URL or code, paste it into the waiting terminal prompt, and press **Enter**.
7. The script will complete the OAuth exchange and automatically save your token to `.lmz/app/secrets/auth/pixiv/refresh_token.txt`.

### Method B: Cookies (Fallback)
If Pixiv OAuth is not set up, or if you encounter issues, the downloader will automatically fall back to using browser cookies if present:
1. Log in to `pixiv.net` in your browser.
2. Export your cookies using the **"Get cookies.txt LOCALLY"** extension.
3. Save the exported file directly as:
   `.lmz/app/secrets/auth/pixiv/cookies.txt`

---

## Security Warning

> [!CAUTION]
> Cookie files and refresh tokens contain your active login sessions.
> * **Never** commit the `secrets/` folder to git. The project's `.gitignore` is pre-configured to exclude it.
> * Never share cookie values or token files.
