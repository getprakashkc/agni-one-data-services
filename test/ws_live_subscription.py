"""
Quick WebSocket subscription test for live prices.

Usage:
    pip install websocket-client
    python test/ws_live_subscription.py
"""

import json
import os
import sys
import time
from websocket import create_connection

WS_URL = "wss://agin-one-data.hi.agni.cash/ws"
INSTRUMENTS = [
    "NSE_INDEX|Nifty 50",
    "NSE_INDEX|Nifty Bank",
]


def main():
    print(f"Connecting to {WS_URL} ...")
    # Keep the socket open; don't auto-timeout while waiting for ticks
    ws = create_connection(WS_URL, timeout=None)

    try:
        welcome = ws.recv()
        print("WELCOME:", welcome)

        subscribe_msg = {"action": "subscribe", "instruments": INSTRUMENTS}
        ws.send(json.dumps(subscribe_msg))
        print("SUBSCRIBED:", ws.recv())

        print("Streaming live messages (Ctrl+C to exit)...")

        latest = {}
        last_print = 0.0
        print_interval = 1.0  # seconds

        while True:
            msg = ws.recv()  # blocks until a message arrives
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                print("RAW:", msg)
                continue

            if payload.get("type") == "market_data":
                data = payload.get("data", {})
                inst = data.get("instrument_key", "")
                ltp = data.get("ltp", "")
                cp = data.get("change_percent", "")
                ltt = data.get("ltt", "")
                ts = data.get("timestamp", "")
                latest[inst] = {
                    "ltp": ltp,
                    "cp": cp,
                    "ltt": ltt,
                    "ts": ts,
                }

                now = time.time()
                if now - last_print >= print_interval:
                    last_print = now
                    # Clear screen and print a compact table of latest values
                    os.system("cls" if os.name == "nt" else "clear")
                    print("Streaming live messages (Ctrl+C to exit)...")
                    print(f"{'#':<4} {'Instrument':<20} {'LTP':>12} {'CP%':>8} {'LTT':>14} {'Timestamp':>22}")
                    print("-" * 86)
                    # Print in preferred order (INSTRUMENTS first), then any others
                    ordered_keys = INSTRUMENTS + sorted(k for k in latest.keys() if k not in INSTRUMENTS)
                    for idx, inst_key in enumerate(ordered_keys, start=1):
                        entry = latest.get(inst_key, {})
                        print(
                            f"{idx:<4} "
                            f"{inst_key:<20} "
                            f"{entry.get('ltp',''):>12} "
                            f"{entry.get('cp',''):>8} "
                            f"{entry.get('ltt',''):>14} "
                            f"{entry.get('ts',''):>22}"
                        )
            else:
                # For other message types, just show the JSON briefly
                print(payload)

    except KeyboardInterrupt:
        print("Interrupted, closing.")
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        ws.close()


if __name__ == "__main__":
    main()
