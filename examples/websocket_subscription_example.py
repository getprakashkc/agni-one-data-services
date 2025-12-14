#!/usr/bin/env python3
"""
Example: How to use WebSocket subscriptions with the Data Service

This example demonstrates how to:
1. Connect to the WebSocket endpoint
2. Subscribe to specific instruments
3. Receive filtered market data
4. Manage subscriptions dynamically
"""

import asyncio
import json
import websockets
from typing import Set

async def websocket_client_example():
    """Example WebSocket client with selective subscriptions"""
    
    uri = "ws://localhost:8001/ws"
    client_id = None
    subscriptions: Set[str] = set()
    message_queue = asyncio.Queue()
    
    try:
        async with websockets.connect(uri) as websocket:
            print("🔗 Connected to Data Service WebSocket")
            
            # Single message receiver that handles all messages
            async def receive_messages():
                """Receive all messages and put them in the queue"""
                try:
                    async for message in websocket:
                        await message_queue.put(message)
                except websockets.exceptions.ConnectionClosed:
                    await message_queue.put(None)  # Signal connection closed
                except Exception as e:
                    print(f"   ❌ Receive error: {e}")
                    await message_queue.put(None)
            
            # Start message receiver
            receive_task = asyncio.create_task(receive_messages())
            
            # Helper function to wait for and process a message
            async def wait_for_message(timeout=5):
                """Wait for a message from the queue"""
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=timeout)
                    if message is None:
                        return None
                    return json.loads(message)
                except asyncio.TimeoutError:
                    return None
            
            # Helper function to process and display messages
            def process_message(data):
                """Process and display a message"""
                msg_type = data.get("type")
                
                if msg_type == "connection":
                    return data  # Return connection message
                elif msg_type == "market_data":
                    instrument = data.get("data", {}).get("instrument_key")
                    ltp = data.get("data", {}).get("ltp")
                    print(f"   📊 {instrument}: ₹{ltp}")
                elif msg_type == "subscription_update":
                    instruments = data.get("instruments", [])
                    action = data.get("action", "")
                    success = data.get("success", False)
                    current_subs = data.get("current_subscriptions", [])
                    if success:
                        print(f"   ✅ {action.capitalize()} successful: {instruments}")
                        print(f"      Current subscriptions: {current_subs}")
                    else:
                        print(f"   ❌ {action.capitalize()} failed: {instruments}")
                elif msg_type == "subscriptions":
                    current_subs = data.get("current_subscriptions", [])
                    print(f"   📋 Current subscriptions: {current_subs}")
                elif msg_type == "pong":
                    print(f"   💓 Pong received")
                elif msg_type == "error":
                    print(f"   ❌ Error: {data.get('message')}")
                else:
                    print(f"   ℹ️  {msg_type}: {data}")
                
                return data
            
            # Wait for welcome message
            welcome_data = await wait_for_message()
            if welcome_data:
                client_id = welcome_data.get("client_id")
                subscriptions = set(welcome_data.get("current_subscriptions", []))
                print(f"✅ Connection established!")
                print(f"   Client ID: {client_id}")
                print(f"   Initial subscriptions: {subscriptions}")
                print()
            
            # Example 1: Subscribe to specific instruments
            print("📊 Subscribing to Nifty 50 and Bank Nifty...")
            subscribe_msg = {
                "action": "subscribe",
                "instruments": [
                    "NSE_INDEX|Nifty 50",
                    "NSE_INDEX|Nifty Bank"
                ]
            }
            await websocket.send(json.dumps(subscribe_msg))
            
            # Wait for confirmation
            response = await wait_for_message(timeout=2)
            if response:
                process_message(response)
            print()
            
            # Example 2: Listen for market data (for 10 seconds)
            print("📈 Listening for market data updates (10 seconds)...")
            print("   (You'll only receive updates for subscribed instruments)")
            print()
            
            # Process messages for 10 seconds
            end_time = asyncio.get_event_loop().time() + 10
            while asyncio.get_event_loop().time() < end_time:
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                    if message is None:
                        print("   🔌 Connection closed")
                        break
                    data = json.loads(message)
                    process_message(data)
                except asyncio.TimeoutError:
                    continue  # Continue waiting
            
            # Example 3: Unsubscribe from one instrument
            print("\n🔕 Unsubscribing from Nifty 50...")
            unsubscribe_msg = {
                "action": "unsubscribe",
                "instruments": ["NSE_INDEX|Nifty 50"]
            }
            await websocket.send(json.dumps(unsubscribe_msg))
            
            # Wait for confirmation
            response = await wait_for_message(timeout=2)
            if response:
                process_message(response)
            print()
            
            # Example 4: Get current subscriptions
            print("📋 Getting current subscriptions...")
            get_subs_msg = {"action": "get_subscriptions"}
            await websocket.send(json.dumps(get_subs_msg))
            
            # Wait for response
            response = await wait_for_message(timeout=2)
            if response:
                process_message(response)
            print()
            
            # Example 5: Subscribe to all instruments
            print("🌐 Subscribing to all instruments...")
            subscribe_all_msg = {
                "action": "subscribe",
                "instruments": ["*"]
            }
            await websocket.send(json.dumps(subscribe_all_msg))
            
            # Wait for confirmation
            response = await wait_for_message(timeout=2)
            if response:
                process_message(response)
            print()
            
            # Listen for a few more seconds
            print("📈 Listening for all market data (5 seconds)...")
            end_time = asyncio.get_event_loop().time() + 5
            while asyncio.get_event_loop().time() < end_time:
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                    if message is None:
                        print("   🔌 Connection closed")
                        break
                    data = json.loads(message)
                    process_message(data)
                except asyncio.TimeoutError:
                    continue  # Continue waiting
            
            # Cancel receive task
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
            
            print("\n✅ Example completed!")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 WebSocket Subscription Example")
    print("=" * 50)
    print()
    print("Make sure the Data Service is running on localhost:8001")
    print()
    
    try:
        asyncio.run(websocket_client_example())
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
