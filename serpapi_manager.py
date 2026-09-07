"""
SerpApi Round-Robin Key Manager
Handles 6 keys with automatic rotation on 429/401/timeout
"""
import os
import time
import logging
from typing import Optional, List
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger(__name__)

@dataclass
class SerpApiKey:
    key: str
    healthy: bool = True
    last_used: float = 0
    error_count: int = 0
    last_error: str = ""

class SerpApiKeyManager:
    """Round-robin SerpApi key manager with automatic failover"""
    
    def __init__(self, keys: List[str]):
        self.keys = [SerpApiKey(k.strip()) for k in keys if k.strip()]
        self.current_index = 0
        self.lock = Lock()
        
        if not self.keys:
            raise ValueError("No SerpApi keys provided")
        
        logger.info(f"Initialized SerpApi key manager with {len(self.keys)} keys")
    
    def get_active_key(self) -> Optional[str]:
        """Get next healthy key in round-robin fashion"""
        with self.lock:
            if not self.keys:
                return None
            
            healthy_keys = [k for k in self.keys if k.healthy]
            if not healthy_keys:
                logger.warning("All keys exhausted, resetting health")
                for k in self.keys:
                    k.healthy = True
                    k.error_count = 0
                healthy_keys = self.keys
            
            # Round-robin from current index
            for _ in range(len(self.keys)):
                key = self.keys[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.keys)
                
                if key.healthy:
                    key.last_used = time.time()
                    return key.key
            
            return None
    
    def mark_key_failed(self, key: str, error: str):
        """Mark key as failed, trigger failover"""
        with self.lock:
            for k in self.keys:
                if k.key == key:
                    k.error_count += 1
                    k.last_error = error
                    logger.warning(f"Key {key[:8]}... failed ({k.error_count}x): {error}")
                    
                    # Mark unhealthy after 2 failures
                    if k.error_count >= 2:
                        k.healthy = False
                        logger.error(f"Key {key[:8]}... marked unhealthy after {k.error_count} failures")
                    break
    
    def get_stats(self) -> dict:
        return {
            "total_keys": len(self.keys),
            "healthy_keys": sum(1 for k in self.keys if k.healthy),
            "keys": [
                {
                    "key_prefix": k.key[:8] + "...",
                    "healthy": k.healthy,
                    "error_count": k.error_count,
                    "last_error": k.last_error,
                    "last_used": k.last_used
                }
                for k in self.keys
            ]
        }


# Global instance - initialize with your 5 keys
SERP_API_KEYS = [
    os.getenv("SERP_API_KEY_1"),
    os.getenv("SERP_API_KEY_2"),
    os.getenv("SERP_API_KEY_3"),
    os.getenv("SERP_API_KEY_4"),
    os.getenv("SERP_API_KEY_5"),
]

key_manager = SerpApiKeyManager([k for k in SERP_API_KEYS if k])