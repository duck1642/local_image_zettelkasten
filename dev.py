import subprocess
import sys
import time
import os
import signal
from pathlib import Path

def run():
    # 1. Paths
    root = Path(__file__).parent
    api_script = root / "backend" / "web_api.py"
    frontend_dir = root / "frontend"
    
    print("🚀 Starting LIZ Development Stack...")

    # 2. Start Python API
    print("--- Starting Python FastAPI (Backend) ---")
    api_proc = subprocess.Popen(
        [sys.executable, str(api_script)],
        cwd=str(root / "backend"),
        env=os.environ.copy()
    )

    # Give the API a moment to start
    time.sleep(2)

    # 3. Start Tauri Dev
    print("--- Starting Tauri (Frontend) ---")
    try:
        # We use shell=True on Windows to handle npm
        tauri_proc = subprocess.Popen(
            ["npm", "run", "tauri", "dev"],
            cwd=str(frontend_dir),
            shell=True
        )

        # 4. Wait for Tauri to finish
        tauri_proc.wait()

    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    finally:
        # 5. Cleanup
        print("--- Cleaning up processes ---")
        if os.name == 'nt':
            # On Windows, Uvicorn (with reload) spawns child processes that survive 
            # a simple terminate(). We must kill the entire process tree.
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(api_proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            api_proc.terminate()
            try:
                api_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_proc.kill()
        print("✅ Done.")

if __name__ == "__main__":
    run()
