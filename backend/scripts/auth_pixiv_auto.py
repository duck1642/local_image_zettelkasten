
import re
import urllib.request
import urllib.parse
import json

from scripts.auth_pixiv import generate_pkce, save_token, CLIENT_ID, CLIENT_SECRET

def run_auth_auto():

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\na Playwright is not installed.")
        print("   Install it with:")
        print("     pip install playwright")
        print("     playwright install chromium")
        print("\n   Falling back to manual authentication...\n")
        from scripts.auth_pixiv import run_auth
        run_auth()
        return

    print("\nY  LMZ Pixiv Authenticator (Auto Mode) Y ")
    print("-------------------------------------------")
    print("A browser window will open. Log in to your Pixiv account.")
    print("The auth code will be captured automatically - no F12 needed!\n")

    verifier, challenge = generate_pkce()

    login_url = (
        f"https://app-api.pixiv.net/web/v1/login"
        f"?code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&client=pixiv-android"
    )

    captured_code = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        def handle_request(request):
            nonlocal captured_code
            url = request.url
            if 'code=' in url:
                match = re.search(r'code=([^&\s]+)', url)
                if match:
                    captured_code = match.group(1)
                    print(f"\n[OK] Auth code captured automatically!")

        def handle_response(response):
            nonlocal captured_code
            if captured_code:
                return
            try:
                headers = response.headers
                location = headers.get('location', '')
                if 'code=' in location:
                    match = re.search(r'code=([^&\s]+)', location)
                    if match:
                        captured_code = match.group(1)
                        print(f"\n[OK] Auth code captured from redirect!")
            except Exception:
                pass

        def handle_route(route):
            nonlocal captured_code
            url = route.request.url
            if url.startswith('pixiv://'):
                match = re.search(r'code=([^&\s]+)', url)
                if match:
                    captured_code = match.group(1)
                    print(f"\n[OK] Auth code intercepted from pixiv:// redirect!")
                route.abort()
            else:
                route.continue_()


        page.on('request', handle_request)
        page.on('response', handle_response)
        page.route('**/*', handle_route)

        print(f"Y Opening Pixiv login page...")

        try:
            page.goto(login_url, wait_until='domcontentloaded', timeout=60000)
        except Exception:
            pass

        print("a3 Waiting for you to log in... (the browser window should be open)")
        print("   Close the browser window to cancel.\n")

        timeout_seconds = 300
        poll_interval = 1000
        elapsed = 0

        while not captured_code and elapsed < timeout_seconds * 1000:
            try:
                page.wait_for_timeout(poll_interval)
                elapsed += poll_interval

                try:
                    current_url = page.url
                    if 'code=' in current_url:
                        match = re.search(r'code=([^&\s]+)', current_url)
                        if match:
                            captured_code = match.group(1)
                            print(f"\n[OK] Auth code found in page URL!")
                except Exception:
                    pass

            except Exception:
                break

        try:
            browser.close()
        except Exception:
            pass

    if not captured_code:
        print("\na Could not capture the auth code.")
        print("   The browser may have been closed before login completed.")
        print("   You can try again, or use the manual method: python auth_pixiv.py --manual")
        return

    print(f"Y Code captured: {captured_code[:8]}... Negotiating with Pixiv servers...")

    data = urllib.parse.urlencode({
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': captured_code,
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
                print(f"\nYZ Success! Your Pixiv Refresh Token has been securely saved to .secrets.yaml.")
                print("   LMZ will now automatically authenticate and download from Pixiv.")
            else:
                print(f"\na Failed to extract refresh_token from response.")
                print(f"   Response: {json.dumps(resp_data, indent=2)[:200]}")
    except urllib.error.HTTPError as e:
        error_info = e.read().decode('utf-8')
        print(f"\na Network error during authentication: HTTP {e.code} - {error_info}")
    except Exception as e:
        print(f"\na An unexpected error occurred: {e}")

if __name__ == '__main__':
    run_auth_auto()
