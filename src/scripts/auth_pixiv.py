
import base64
import hashlib
import os
import re
import urllib.request
import urllib.parse
import json
from pathlib import Path
from utils import SECRETS_DIR

CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"

def generate_pkce():


    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('utf-8')).digest()).decode('utf-8').rstrip('=')
    return verifier, challenge

def run_auth():

    print("\n LIZ Pixiv Authenticator ")
    print("------------------------------")
    print("This tool will securely generate a Pixiv Refresh Token so LIZ can bypass API walls.")

    verifier, challenge = generate_pkce()

    login_url = f"https://app-api.pixiv.net/web/v1/login?code_challenge={challenge}&code_challenge_method=S256&client=pixiv-android"

    print(f"\n1  Open this secure login link in your browser:")
    print(f"\n    {login_url}\n")
    print(f"2   BEFORE logging in, press F12 to open Developer Tools and go to the 'Network' tab.")
    print(f"3  Log in to your Pixiv account.")
    print(f"4  After logging in, your browser may say 'Link not recognized' or 'Address wasn't understood' (because of the pixiv:// protocol). THIS IS NORMAL!")
    print(f"5  Look at the F12 Network tab. Find a request that starts with 'callback?state=...'")
    print(f"6  Click that request, look at its URL or Payload, and find the 'code=' parameter.")
    print(f"    Copy the code (or the entire URL) and paste it below.\n")

    try:
        url_input = input("Paste the URL or code here: ").strip()
    except KeyboardInterrupt:
        print("\nAuthentication cancelled.")
        return

    if "code=" in url_input:
        match = re.search(r'code=([^&\s]+)', url_input)
        if not match:
            print(f"\n Could not extract code from: {url_input}")
            return
        code = match.group(1)
    elif len(url_input) > 10 and "://" not in url_input:
        code = url_input
    else:
        print(f"\n Could not find 'code=' in the input provided: {url_input}")
        print("Please make sure you copied the exact URL after logging in.")
        return

    print(f"\n Authentication code extracted: {code[:5]}... Negotiating with Pixiv servers...")

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
                print(f" Success! Your Pixiv Refresh Token has been securely saved to .secrets.yaml.")
                print("   LIZ will now automatically authenticate and download from Pixiv.")
            else:
                print(f"\n Failed to extract refresh_token from response.")
    except urllib.error.HTTPError as e:
        error_info = e.read().decode('utf-8')
        print(f"\n Network error during authentication: HTTP {e.code} - {error_info}")
    except Exception as e:
        print(f"\n An unexpected error occurred: {e}")

def save_token(token):

    secrets_path = SECRETS_DIR / ".secrets.yaml"

    if secrets_path.exists():
        with open(secrets_path, 'r', encoding='utf-8') as f:
            content = f.read()


        new_content = re.sub(r'pixiv_token:\s*".*"', f'pixiv_token: "{token}"', content)
        if new_content == content:
            new_content = re.sub(r'pixiv_token:\s*.*', f'pixiv_token: "{token}"', content)
    else:

        new_content = (
            "# LIZ Secrets  Sensitive credentials\n"
            "# This file contains sensitive credentials. Do not share it.\n\n"
            f'pixiv_token: "{token}"\n'
        )

    with open(secrets_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == '__main__':
    run_auth()
