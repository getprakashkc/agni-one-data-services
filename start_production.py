#!/usr/bin/env python3
"""
Production startup script for Agnidata Trading Services
Optimized for Coolify deployment
"""

import os
import sys
import time
import signal
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionServiceManager:
    def __init__(self):
        self.processes = []
        self.running = True
        
        # Environment variables
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_db = int(os.getenv('REDIS_DB', '0'))
        
        # Service ports
        self.token_port = int(os.getenv('TOKEN_SERVICE_PORT', '8000'))
        self.data_port = int(os.getenv('DATA_SERVICE_PORT', '8001'))
        self.trading_port = int(os.getenv('TRADING_SERVICE_PORT', '8002'))
        self.app_port = int(os.getenv('TRADING_APP_PORT', '8003'))
        
        # Service hosts
        self.token_host = os.getenv('TOKEN_SERVICE_HOST', '0.0.0.0')
        self.data_host = os.getenv('DATA_SERVICE_HOST', '0.0.0.0')
        self.trading_host = os.getenv('TRADING_SERVICE_HOST', '0.0.0.0')
        self.app_host = os.getenv('TRADING_APP_HOST', '0.0.0.0')
        
        # Internal API configuration
        self.internal_api_base = os.getenv('INTERNAL_API_BASE_URL', 'http://192.168.1.206:9000')
        self.account_id = os.getenv('INTERNAL_API_ACCOUNT_ID', 'agnidata001')
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.stop_all_services()
        sys.exit(0)
    
    def wait_for_redis(self, timeout=60):
        """Wait for Redis to be available"""
        import redis
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                r = redis.Redis(host=self.redis_host, port=self.redis_port, db=self.redis_db)
                r.ping()
                logger.info("✅ Redis is available")
                return True
            except Exception as e:
                logger.info(f"⏳ Waiting for Redis... ({e})")
                time.sleep(2)
        
        logger.error("❌ Redis not available after timeout")
        return False
    
    def start_service(self, name, script_path, port, host='0.0.0.0'):
               """Start a service in a subprocess"""
        try:
            logger.info(f"🚀 Starting {name} on {host}:{port}")
            
            # Set environment variables for the service
            env = os.environ.copy()
            env.update({
                'REDIS_HOST': self.redis_host,
                'REDIS_PORT': str(self.redis_port),
                'REDIS_DB': str(self.redis_db),
                'INTERNAL_API_BASE_URL': self.internal_api_base,
                'INTERNAL_API_ACCOUNT_ID': self.account_id
            })
            
            process = subprocess.Popen(
                [sys.executable, script_path],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes.append((name, process))
            logger.info(f"✅ {name} started (PID: {process.pid})")
            return process
            
        except Exception as e:
            logger.error(f"❌ Failed to start {name}: {e}")
            return None
    
    def start_all_services(self):
        """Start all trading services"""
        logger.info("🚀 Starting Agnidata Trading Services (Production Mode)")
        logger.info("=" * 60)
        
        # Wait for Redis
        if not self.wait_for_redis():
            logger.error("❌ Cannot start services without Redis")
            return False
        
        # Start services in order
        services = [
            ("Token Service", "src/services/token_service.py", self.token_port, self.token_host),
            ("Data Service", "src/services/data_service.py", self.data_port, self.data_host),
            ("Trading Service", "src/services/trading_service.py", self.trading_port, self.trading_host),
            ("Trading App", "src/services/trading_app.py", self.app_port, self.app_host),
        ]
        
        for name, script, port, host in services:
            process = self.start_service(name, script, port, host)
            if process:
                # Wait a bit between services
                time.sleep(3)
            else:
                logger.error(f"❌ Failed to start {name}")
                return False
        
        logger.info("✅ All services started successfully!")
        return True
    
    def monitor_services(self):
        """Monitor running services"""
        logger.info("📊 Service Status:")
        logger.info("🔗 Service URLs:")
        logger.info(f"   Token Service: http://localhost:{self.token_port}")
        logger.info(f"   Data Service: http://localhost:{self.data_port}")
        logger.info(f"   Trading Service: http://localhost:{self.trading_port}")
        logger.info(f"   Trading App: http://localhost:{self.app_port}")
        logger.info("")
        
        while self.running:
            try:
                # Check if any process has died
                for name, process in self.processes[:]:
                    if process.poll() is not None:
                        logger.error(f"❌ {name} has stopped unexpectedly")
                        self.processes.remove((name, process))
                
                # If all processes are dead, exit
                if not self.processes:
                    logger.error("❌ All services have stopped")
                    break
                
                time.sleep(10)  # Check every 10 seconds
                
            except KeyboardInterrupt:
                logger.info("🛑 Received interrupt signal")
                break
            except Exception as e:
                logger.error(f"❌ Error monitoring services: {e}")
                break
    
    def stop_all_services(self):
        """Stop all running services"""
        logger.info("🛑 Stopping all services...")
        
        for name, process in self.processes:
            try:
                logger.info(f"🛑 Stopping {name}...")
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=10)
                    logger.info(f"✅ {name} stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ {name} didn't stop gracefully, forcing...")
                    process.kill()
                    process.wait()
                    logger.info(f"🔪 {name} force stopped")
                    
            except Exception as e:
                logger.error(f"❌ Error stopping {name}: {e}")
        
        self.processes.clear()
        logger.info("✅ All services stopped")
    
    def run(self):
        """Main execution loop"""
        try:
            # Start all services
            if not self.start_all_services():
                logger.error("❌ Failed to start services")
                return 1
            
            # Monitor services
            self.monitor_services()
            
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            return 1
        
        finally:
            # Cleanup
            self.stop_all_services()
        
        return 0

def main():
    """Main entry point"""
    manager = ProductionServiceManager()
    return manager.run()

if __name__ == "__main__":
    sys.exit(main())


