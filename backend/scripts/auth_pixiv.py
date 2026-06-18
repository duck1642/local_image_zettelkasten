import sys
import base64
import hashlib
import os
import re
import urllib.request
import urllib.parse
import json
from pathlib import Path

# Add backend directory to sys.path so utils can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import app_auth_root

CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"

def generate_pkce():


    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('utf-8')).digest()).decode('utf-8').rstrip('=')
    return verifier, challenge

def run_auth():

    print("\n[INFO] LMZ Pixiv Authenticator")
    print("------------------------------")
    print("This tool will securely generate a Pixiv Refresh Token so LMZ can bypass API walls.")

    verifier, challenge = generate_pkce()

    login_url = f"https://app-api.pixiv.net/web/v1/login?code_challenge={challenge}&code_challenge_method=S256&client=pixiv-android"

    print(f"\n[INFO] 1. Open this secure login link in your browser:")
    print(f"\n    {login_url}\n")
    print("2. BEFORE logging in, press F12 to open Developer Tools and go to the 'Network' tab.")
    print("3. Log in to your Pixiv account.")
    print("4. After logging in, your browser may say 'Link not recognized' or 'Address was not understood' because of the pixiv:// protocol. This is normal.")
    print("5. Look at the F12 Network tab. Find a request that starts with 'callback?state=...'")
    print("6. Click that request, look at its URL or Payload, and find the 'code=' parameter.")
    print(f"    Copy the code (or the entire URL) and paste it below.\n")

    try:
        url_input = input("Paste the URL or code here: ").strip()
    except KeyboardInterrupt:
        print("\nAuthentication cancelled.")
        return

    if "code=" in url_input:
        match = re.search(r'code=([^&\s]+)', url_input)
        if not match:
            print(f"\n[ERROR] Could not extract code from: {url_input}")
            return
        code = match.group(1)
    elif len(url_input) > 10 and "://" not in url_input:
        code = url_input
    else:
        print(f"\n[ERROR] Could not find 'code=' in the input provided: {url_input}")
        print("Please make sure you copied the exact URL after logging in.")
        return

    print(f"\n[INFO] Authentication code extracted: {code[:5]}... Negotiating with Pixiv servers...")

    data = urllib.parse.urlencode({
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'code_verifier': verifier,
        'redirect_uri': 'https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback',
        'include_policy': 'true'
    }).encode('utf-8')

    req = urllib.request.Request('https://oauth.secure.pixiv.net/auth/token', data=data)
    req.add_header('User-Agent', 'PixivAndroidApp/5.0.234 (Android 11; Pixel 5)')

    try:
        with urllib.request.urlopen(req) as response:
            resp_data = json.loads(response.read().decode('utf-8'))
            refresh_token = resp_data.get('response', {}).get('refresh_token')

            if refresh_token:
                save_token(refresh_token)
                print("[OK] Your Pixiv Refresh Token has been securely saved.")
                print("   LMZ will now automatically authenticate and download from Pixiv.")
            else:
                print("\n[ERROR] Failed to extract refresh_token from response.")
    except urllib.error.HTTPError as e:
        error_info = e.read().decode('utf-8')
        print(f"\n[ERROR] Network error during authentication: HTTP {e.code} - {error_info}")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")

def save_token(token):
    token_dir = app_auth_root() / "pixiv"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / "refresh_token.txt"
    token_path.write_text(token, encoding="utf-8")
    print(f"[OK] Saved token to: {token_path}")

if __name__ == '__main__':
    run_auth()
