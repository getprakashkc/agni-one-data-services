"""
Quick WebSocket subscription test for live prices.

Usage:
    pip install websocket-client
    python test/ws_live_subscription.py
"""

import json
import sys
from websocket import create_connection

WS_URL = "wss://agin-one-data.hi.agni.cash/ws"
INSTRUMENTS = [
    "NSE_FO|48261",
    "NSE_FO|48262",
    "NSE_FO|48265",
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
        while True:
            msg = ws.recv()  # blocks until a message arrives
            print("MSG:", msg)

    except KeyboardInterrupt:
        print("Interrupted, closing.")
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        ws.close()


if __name__ == "__main__":
    main()
