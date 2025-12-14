#!/usr/bin/env python3
"""
Endpoint Viewer - View all available endpoints and WebSockets
"""

import requests
import json
from typing import Dict, List, Any
import asyncio
import websockets
from datetime import datetime

class EndpointViewer:
    def __init__(self):
        self.services = {
            "token_service": {"port": 8000, "name": "Token Management Service"},
            "data_service": {"port": 8001, "name": "Data Service"},
            "trading_service": {"port": 8002, "name": "Trading Service"},
            "trading_app": {"port": 8003, "name": "Trading Application"}
        }
        
    def check_service_health(self, service_name: str, port: int) -> Dict[str, Any]:
        """Check if service is running and get health status"""
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=5)
            if response.status_code == 200:
                return {
                    "status": "running",
                    "health": response.json(),
                    "response_time": response.elapsed.total_seconds()
                }
            else:
                return {
                    "status": "error",
                    "error": f"HTTP {response.status_code}",
                    "response_time": response.elapsed.total_seconds()
                }
        except requests.exceptions.ConnectionError:
            return {"status": "not_running", "error": "Connection refused"}
        except requests.exceptions.Timeout:
            return {"status": "timeout", "error": "Request timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_openapi_spec(self, port: int) -> Dict[str, Any]:
        """Get OpenAPI specification for a service"""
        try:
            response = requests.get(f"http://localhost:{port}/openapi.json", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def extract_endpoints(self, openapi_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract endpoints from OpenAPI spec"""
        endpoints = []
        
        if "paths" in openapi_spec:
            for path, methods in openapi_spec["paths"].items():
                for method, details in methods.items():
                    if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        endpoint = {
                            "path": path,
                            "method": method.upper(),
                            "summary": details.get("summary", ""),
                            "description": details.get("description", ""),
                            "tags": details.get("tags", []),
                            "parameters": details.get("parameters", []),
                            "responses": list(details.get("responses", {}).keys())
                        }
                        endpoints.append(endpoint)
        
        return endpoints
    
    def extract_websockets(self, openapi_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract WebSocket endpoints from OpenAPI spec"""
        websockets = []
        
        if "paths" in openapi_spec:
            for path, methods in openapi_spec["paths"].items():
                for method, details in methods.items():
                    if method.lower() == "websocket":
                        ws_endpoint = {
                            "path": path,
                            "method": "WEBSOCKET",
                            "summary": details.get("summary", ""),
                            "description": details.get("description", ""),
                            "tags": details.get("tags", [])
                        }
                        websockets.append(ws_endpoint)
        
        return websockets
    
    async def test_websocket_connection(self, port: int, ws_path: str) -> Dict[str, Any]:
        """Test WebSocket connection"""
        try:
            uri = f"ws://localhost:{port}{ws_path}"
            async with websockets.connect(uri, timeout=5) as websocket:
                return {
                    "status": "connected",
                    "uri": uri,
                    "connection_time": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "status": "failed",
                "uri": f"ws://localhost:{port}{ws_path}",
                "error": str(e)
            }
    
    def display_service_info(self, service_name: str, port: int):
        """Display comprehensive service information"""
        print(f"\n{'='*60}")
        print(f"🔍 {self.services[service_name]['name']} (Port {port})")
        print(f"{'='*60}")
        
        # Check health
        health_status = self.check_service_health(service_name, port)
        print(f"📊 Health Status: {health_status['status']}")
        
        if health_status['status'] == 'running':
            print(f"⏱️  Response Time: {health_status.get('response_time', 0):.3f}s")
            if 'health' in health_status:
                print(f"💚 Health Data: {health_status['health']}")
        
        # Get OpenAPI spec
        openapi_spec = self.get_openapi_spec(port)
        
        if "error" not in openapi_spec:
            # Extract endpoints
            endpoints = self.extract_endpoints(openapi_spec)
            websockets = self.extract_websockets(openapi_spec)
            
            print(f"\n📡 REST Endpoints ({len(endpoints)}):")
            for endpoint in endpoints:
                print(f"  {endpoint['method']:8} {endpoint['path']}")
                if endpoint['summary']:
                    print(f"           📝 {endpoint['summary']}")
                if endpoint['tags']:
                    print(f"           🏷️  Tags: {', '.join(endpoint['tags'])}")
                print()
            
            print(f"\n🔌 WebSocket Endpoints ({len(websockets)}):")
            for ws in websockets:
                print(f"  {ws['method']:8} {ws['path']}")
                if ws['summary']:
                    print(f"           📝 {ws['summary']}")
                print()
            
            # Display documentation URLs
            print(f"\n📚 Documentation:")
            print(f"  🔗 Swagger UI: http://localhost:{port}/docs")
            print(f"  🔗 ReDoc: http://localhost:{port}/redoc")
            print(f"  🔗 OpenAPI JSON: http://localhost:{port}/openapi.json")
            
        else:
            print(f"❌ Cannot fetch OpenAPI spec: {openapi_spec['error']}")
    
    def display_all_services(self):
        """Display information for all services"""
        print("🚀 Agnidata Trading Services - Endpoint Viewer")
        print("=" * 60)
        print(f"🕐 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        for service_name, info in self.services.items():
            self.display_service_info(service_name, info['port'])
        
        print(f"\n{'='*60}")
        print("🎯 Quick Access URLs:")
        print("  🔗 Token Service: http://localhost:8000/docs")
        print("  🔗 Data Service: http://localhost:8001/docs")
        print("  🔗 Trading Service: http://localhost:8002/docs")
        print("  🔗 Trading App: http://localhost:8003/docs")
        print(f"{'='*60}")

def main():
    """Main function to run endpoint viewer"""
    viewer = EndpointViewer()
    viewer.display_all_services()

if __name__ == "__main__":
    main()


