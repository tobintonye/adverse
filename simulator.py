"""
Android Box or any media player Simulator

Simulates the full lifecycle of a physical Android player device.
Run this during development instead of a real Android box.

Usage:
    python simulator.py                         # auto-generates a device UID
    python simulator.py --uid BOX-DEV-001       # use a specific UID
    python simulator.py --uid BOX-DEV-001 --token <auth_token>  # resume a paired session

What it does:
    1. Registers with the API (POST /players/register/)
    2. Displays the pairing code — you enter it in the dashboard
    3. Polls until paired (GET /players/register/status/)
    4. Saves the auth token to .simulator_state.json
    5. Starts the main loop:
         - heartbeat every 30s
         - fetch schedule every 60s
         - simulate playback and POST logs
         - POST metrics every 60s
"""
import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

# media player sim for dev only
BASE_URL = "http://localhost:8000/adverse-api/billboards"
STATE_FILE = ".simulator_state.json"

HEARTBEAT_INTERVAL = 30     # seconds
SCHEDULE_INTERVAL = 60      # seconds
METRICS_INTERVAL = 60       # seconds
POLL_INTERVAL = 5           # seconds — how often to poll for pairing

import requests

def log(tag, msg, color=None):
    colors = {"green": "\033[92m", "yellow": "\033[93m", "red": "\033[91m", "cyan": "\033[96m"}
    reset = "\033[0m"
    prefix = f"{colors.get(color, '')}{tag}{reset}" if color else tag
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {prefix:20s} {msg}")

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
    return {}

# Thin wrapper around requests — handles auth header and errors
def api(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"DeviceToken {token}"
    if "json" in kwargs:
        headers["Content-Type"] = "application/json"
    url = f"{BASE_URL}{path}"
    try:
        res = getattr(requests, method)(url, headers=headers, timeout=10, **kwargs)
        return res
    except requests.ConnectionError:
        log("ERROR", f"Cannot reach {url} — is the server running?", "red")
        return None
    except requests.Timeout:
        log("ERROR", f"Request to {url} timed out.", "red")
        return None
    
# media player Self-registration
def register(device_uid: str) -> dict | None:
    log("REGISTER", f"Registering device_uid={device_uid} ...", "cyan")
    res = api("post", "/players/register/", json={"device_uid": device_uid})
    if res is None: 
        return None
    if res.status_code in (200, 201):
        data = res.json()
        log("REGISTER", f"Got pairing code: {data['pairing_code']}", "green")
        return data
    log("REGISTER", f"Failed: {res.status_code} {res.text}", "red")
    return None

# pairing polling 
def wait_for_pairing(device_uid: str) -> str | None:
    """
    Poll GET /players/register/status/ until paired.
    Returns the auth_token once the ad manager pairs the device.
    """
    log("PAIRING", "Waiting for ad manager to pair this device in the dashboard ...", "yellow")
    log("PAIRING", f"Open the dashboard → Players → Pair Device → enter the code above", "yellow")
    print()
    
    while True: 
        res = api("get", "/players/register/status/", params={"device_uid": device_uid})
        if res is None:
            time.sleep(POLL_INTERVAL)
            continue
        if res.status_code == 200:
            data = res.json()
            if data.get("is_paired"):
                token = data.get("auth_token")
                if token:
                    log("PAIRING", f"Paired! Billboard: {data['billboard']['name']}", "green")
                    log("PAIRING", "Auth token claimed and saved.", "green")
                    return token
                else:
                    log("PAIRING", "Paired but token already claimed. Rotate token from dashboard.", "red")
                    return None
            else:
                log("PAIRING", f"Status: {data.get('status')} — still waiting ...", "yellow")
        else:
            log("PAIRING", f"Poll error: {res.status_code}", "red")

        time.sleep(POLL_INTERVAL)

# Main device loop
def send_heartbeat(token: str, firmware: str):
    res = api("post", "/players/heartbeat/", token=token, json={
        "firmware_version": firmware,
        "free_storage_mb": random.randint(2000, 8000),
        "current_media_id": str(uuid.uuid4()),
    })
    if res and res.status_code == 200:
        data = res.json()
        log("HEARTBEAT", f"OK — status={data['device_status']} billboard={data.get('billboard')}", "green")
    else:
        status_code = res.status_code if res else "no response"
        log("HEARTBEAT", f"Failed: {status_code}", "red")

def run_device_loop(token: str, firmware: str = "sim-1.0.0"):
    """Main loop — runs until Ctrl+C."""
    print()

    last_heartbeat = 0
    
    while True:
        now = time.time()

        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            send_heartbeat(token, firmware)
            last_heartbeat = now

def main():
    parser = argparse.ArgumentParser(description="Simulates an Android billboard player box.")
    parser.add_argument("--uid", default=None, help="Device UID (auto-generated if omitted)")
    parser.add_argument("--token", default=None, help="Skip pairing — use existing auth token")
    parser.add_argument("--firmware", default="sim-1.0.0", help="Firmware version string to report")
    args = parser.parse_args()

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║   Android Box Simulator (Dev Mode)   ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    state = load_state()
    device_uid = args.uid or state.get("device_uid") or f"SIM-{uuid.uuid4().hex[:8].upper()}"
    auth_token = args.token or state.get("auth_token")

    log("BOOT", f"device_uid = {device_uid}", "cyan")

    # --- Fast path: token already known ---
    if auth_token:
        log("BOOT", "Resuming with existing auth token.", "green")
        save_state({"device_uid": device_uid, "auth_token": auth_token})
        try:
            run_device_loop(auth_token, firmware=args.firmware)
        except KeyboardInterrupt:
            print("\n\nSimulator stopped.")
        return

    # --- Full pairing flow ---
    data = register(device_uid)
    if not data:
        sys.exit(1)

    print()
    print("  ┌─────────────────────────────────┐")
    print(f"  │   Pairing Code:  {data['pairing_code']:<14s}  │")
    print("  │                                 │")
    print("  │   Enter this in the dashboard   │")
    print("  └─────────────────────────────────┘")
    print()

    token = wait_for_pairing(device_uid)
    if not token:
        sys.exit(1)

    save_state({"device_uid": device_uid, "auth_token": token})
    log("BOOT", f"State saved to {STATE_FILE}", "green")
    print()

    try:
        run_device_loop(token, firmware=args.firmware)
    except KeyboardInterrupt:
        print("\n\nSimulator stopped.")


if __name__ == "__main__":
    main()
