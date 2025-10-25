#!/usr/bin/env python3
"""
Startup script for Agnidata Trading Services
"""

import subprocess
import sys
import time
import os
from pathlib import Path

def start_service(script_path, service_name):
    """Start a service in a new process"""
    try:
        print(f"🚀 Starting {service_name}...")
        process = subprocess.Popen([sys.executable, script_path], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE,
                                 text=True)
        print(f"✅ {service_name} started (PID: {process.pid})")
        return process
    except Exception as e:
        print(f"❌ Failed to start {service_name}: {e}")
        return None

def main():
    """Main startup function"""
    print("🚀 Starting Agnidata Trading Services")
    print("=" * 50)
    
    # Get the project root directory
    project_root = Path(__file__).parent
    
    # Service configurations
    services = [
        {
            "name": "Token Service",
            "script": "src/services/token_service.py",
            "required": True,
            "wait": 3
        },
        {
            "name": "Options Trading App",
            "script": "src/examples/options_trading_app.py",
            "required": False,
            "wait": 2
        },
        {
            "name": "Redis Monitor",
            "script": "src/examples/redis_monitor.py",
            "required": False,
            "wait": 1
        }
    ]
    
    processes = []
    
    try:
        # Start services
        for service in services:
            script_path = project_root / service["script"]
            
            if not script_path.exists():
                print(f"❌ Script not found: {script_path}")
                if service["required"]:
                    print("❌ Required service failed to start. Exiting.")
                    return
                continue
            
            process = start_service(str(script_path), service["name"])
            if process:
                processes.append((process, service["name"]))
                
                if service["wait"] > 0:
                    print(f"⏳ Waiting {service['wait']} seconds for {service['name']} to initialize...")
                    time.sleep(service["wait"])
            else:
                if service["required"]:
                    print("❌ Required service failed to start. Exiting.")
                    return
        
        print("\n✅ All services started successfully!")
        print("\n📊 Service Status:")
        for process, name in processes:
            print(f"   {name}: Running (PID: {process.pid})")
        
        print("\n🔗 Service URLs:")
        print("   Token Service: http://localhost:8000")
        print("   Redis Insight: http://localhost:8001")
        
        print("\n📋 Available Endpoints:")
        print("   GET  /health - Service health check")
        print("   GET  /token/status - Token status")
        print("   GET  /token/validate - Validate token")
        print("   POST /token/update - Update token manually")
        
        print("\n⏹️  Press Ctrl+C to stop all services")
        
        # Keep running until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping all services...")
            
    except Exception as e:
        print(f"❌ Error starting services: {e}")
    
    finally:
        # Clean up processes
        for process, name in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✅ {name} stopped")
            except:
                try:
                    process.kill()
                    print(f"🔪 {name} force stopped")
                except:
                    print(f"❌ Failed to stop {name}")

if __name__ == "__main__":
    main()
