# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
import redis
import json
import hashlib
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from enum import Enum


class CacheLevel(Enum):
    """Three-tier caching strategy"""
    HOT = "redis"      # Frequent access, real-time data
    WARM = "database"  # Pre-computed results, aggregations
    COLD = "api"       # Complex computations, ML results


def _coerce_level(level):
    """Return a CacheLevel from a CacheLevel, a member name ("hot"/"warm"/"cold"),
    or an enum value ("redis"/"database"/"api").

    The public string API uses member names ("hot"), but the enum values are
    "redis"/"database"/"api"; calling ``CacheLevel("hot")`` therefore raised
    ``'hot' is not a valid CacheLevel``. Resolve by name first, then by value.
    """
    if isinstance(level, CacheLevel):
        return level
    try:
        return CacheLevel[str(level).upper()]
    except KeyError:
        return CacheLevel(level)


class CacheManager:
    """Synchronous 3-tier caching system for AI insights performance optimization.
    
    NOTE: Rewritten from async to sync because Frappe runs under WSGI (Gunicorn),
    which is synchronous. async/await methods cannot be properly awaited in this context.
    The DB-backed warm/cold tiers are kept but writes are batched where possible.
    """
    
    def __init__(self):
        self._redis_client = None  # Lazy init — don't connect until first use
        self.db_cache_table = "Insights Cache"
        self._db_table_checked = False
        self._db_table_exists = False
        self.default_ttl = {
            CacheLevel.HOT: 3600,      # 1 hour for hot cache
            CacheLevel.WARM: 86400,    # 24 hours for warm cache  
            CacheLevel.COLD: 604800    # 7 days for cold cache
        }

    def _ensure_db_table(self) -> bool:
        """Check once whether the Insights Cache table exists."""
        if not self._db_table_checked:
            try:
                self._db_table_exists = frappe.db.table_exists(self.db_cache_table)
            except Exception:
                self._db_table_exists = False
            self._db_table_checked = True
        return self._db_table_exists

    @property
    def redis_client(self):
        """Lazy Redis connection — only connect on first use."""
        if self._redis_client is None:
            self._redis_client = self._get_redis_client()
        return self._redis_client
        
    def _get_redis_client(self):
        """Initialize Redis connection for hot cache"""
        try:
            # Use Frappe's Redis configuration
            redis_config = frappe.get_conf().get("redis_cache", {})
            
            client = redis.Redis(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 13000),
                db=redis_config.get("db", 0),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection
            client.ping()
            return client
            
        except Exception as e:
            frappe.log_error(f"Redis connection failed: {str(e)}")
            return None
    
    def get(self, key: str, cache_levels: List[CacheLevel] = None) -> Optional[Any]:
        """Retrieve data from cache with tier fallback (synchronous)"""
        if cache_levels is None:
            cache_levels = [CacheLevel.HOT, CacheLevel.WARM, CacheLevel.COLD]
        
        for level in cache_levels:
            try:
                result = self._get_from_level(key, level)
                if result is not None:
                    # Promote to higher cache levels for future access
                    self._promote_cache(key, result, level)
                    return result
            except Exception as e:
                frappe.log_error(f"Cache get error at {level}: {str(e)}")
                continue
        
        return None
    
    def set(self, key: str, value: Any, cache_level: CacheLevel = CacheLevel.HOT, 
            ttl: Optional[int] = None, metadata: Dict[str, Any] = None) -> bool:
        """Store data in specified cache tier (synchronous)"""
        try:
            if ttl is None:
                ttl = self.default_ttl[cache_level]
            
            success = self._set_to_level(key, value, cache_level, ttl, metadata)
            
            # Auto-promote valuable data to multiple levels
            if success and cache_level == CacheLevel.COLD:
                # Also store in warm cache with shorter TTL
                self._set_to_level(key, value, CacheLevel.WARM, self.default_ttl[CacheLevel.WARM])
            
            return success
            
        except Exception as e:
            frappe.log_error(f"Cache set error: {str(e)}")
            return False
    
    def _get_from_level(self, key: str, level: CacheLevel) -> Optional[Any]:
        """Get data from specific cache level"""
        
        if level == CacheLevel.HOT and self.redis_client:
            # Redis hot cache
            cached_data = self.redis_client.get(f"hot:{key}")
            if cached_data:
                return json.loads(cached_data)
        
        elif level == CacheLevel.WARM:
            # Skip DB tiers if table doesn't exist
            if not self._ensure_db_table():
                return None
            cache_entry = frappe.db.get_value(
                self.db_cache_table,
                {"cache_key": key, "cache_level": "warm"},
                ["cache_value", "expires_at"],
                as_dict=True
            )
            
            if cache_entry and cache_entry.expires_at > datetime.now():
                try:
                    return json.loads(cache_entry.cache_value)
                except json.JSONDecodeError:
                    return None
        
        elif level == CacheLevel.COLD:
            # Skip DB tiers if table doesn't exist
            if not self._ensure_db_table():
                return None
            cache_entry = frappe.db.get_value(
                self.db_cache_table,
                {"cache_key": key, "cache_level": "cold"},
                ["cache_value", "expires_at", "metadata"],
                as_dict=True
            )
            
            if cache_entry and cache_entry.expires_at > datetime.now():
                try:
                    result = json.loads(cache_entry.cache_value)
                    # Include metadata for complex results
                    if cache_entry.metadata:
                        result["_cache_metadata"] = json.loads(cache_entry.metadata)
                    return result
                except json.JSONDecodeError:
                    return None
        
        return None
    
    def _set_to_level(self, key: str, value: Any, level: CacheLevel, 
                      ttl: int, metadata: Dict[str, Any] = None) -> bool:
        """Set data to specific cache level"""
        
        try:
            if level == CacheLevel.HOT and self.redis_client:
                # Redis hot cache - JSON serializable data only
                cache_data = json.dumps(value)
                return self.redis_client.setex(f"hot:{key}", ttl, cache_data)
            
            else:
                # Database cache for warm and cold tiers
                if not self._ensure_db_table():
                    return False
                expires_at = datetime.now() + timedelta(seconds=ttl)
                
                # Serialize value — JSON only, no pickle for safety
                try:
                    cache_value = json.dumps(value)
                except (TypeError, ValueError):
                    frappe.log_error(f"Cache: cannot JSON-serialize value for key {key}")
                    return False
                
                metadata_json = json.dumps(metadata) if metadata else None

                # Use single SQL upsert pattern instead of get_value + set_value/insert
                existing = frappe.db.get_value(
                    self.db_cache_table,
                    {"cache_key": key, "cache_level": level.value},
                    "name"
                )
                
                if existing:
                    frappe.db.sql("""
                        UPDATE `tabInsights Cache`
                        SET cache_value = %s, expires_at = %s, metadata = %s,
                            access_count = access_count + 1
                        WHERE name = %s
                    """, (cache_value, expires_at, metadata_json, existing))
                else:
                    cache_doc = frappe.get_doc({
                        "doctype": self.db_cache_table,
                        "cache_key": key,
                        "cache_level": level.value,
                        "cache_value": cache_value,
                        "expires_at": expires_at,
                        "metadata": metadata_json,
                        "access_count": 1,
                        "created_by": frappe.session.user
                    })
                    cache_doc.insert(ignore_permissions=True)
                
                frappe.db.commit()
                return True
                
        except Exception as e:
            frappe.log_error(f"Cache set error for {level}: {str(e)}")
            return False
    
    def _promote_cache(self, key: str, value: Any, current_level: CacheLevel):
        """Promote frequently accessed data to higher cache tiers"""
        
        if current_level == CacheLevel.COLD:
            self._set_to_level(key, value, CacheLevel.WARM, self.default_ttl[CacheLevel.WARM])
        
        elif current_level == CacheLevel.WARM and self.redis_client:
            self._set_to_level(key, value, CacheLevel.HOT, self.default_ttl[CacheLevel.HOT])
    
    def delete(self, key: str, cache_levels: List[CacheLevel] = None):
        """Delete data from specified cache levels"""
        if cache_levels is None:
            cache_levels = [CacheLevel.HOT, CacheLevel.WARM, CacheLevel.COLD]
        
        for level in cache_levels:
            try:
                if level == CacheLevel.HOT and self.redis_client:
                    self.redis_client.delete(f"hot:{key}")
                else:
                    frappe.db.delete(self.db_cache_table, {
                        "cache_key": key,
                        "cache_level": level.value
                    }) if self._ensure_db_table() else None
            except Exception as e:
                frappe.log_error(f"Cache delete error for {level}: {str(e)}")
    
    def clear_expired(self):
        """Clean up expired cache entries"""
        if not self._ensure_db_table():
            return
        try:
            # Clean database cache
            frappe.db.delete(self.db_cache_table, {
                "expires_at": ["<", datetime.now()]
            })
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(f"Cache cleanup error: {str(e)}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        stats = {"levels": {}}
        
        # Redis stats
        if self.redis_client:
            try:
                redis_info = self.redis_client.info()
                stats["levels"]["hot"] = {
                    "total_keys": redis_info.get("db0", {}).get("keys", 0),
                    "memory_usage": redis_info.get("used_memory_human", "0B"),
                    "hit_rate": redis_info.get("keyspace_hits", 0) / max(1, redis_info.get("keyspace_hits", 0) + redis_info.get("keyspace_misses", 0)) * 100
                }
            except Exception:
                stats["levels"]["hot"] = {"status": "unavailable"}
        
        # Database cache stats
        try:
            warm_count = frappe.db.count(self.db_cache_table, {"cache_level": "warm", "expires_at": [">", datetime.now()]})
            cold_count = frappe.db.count(self.db_cache_table, {"cache_level": "cold", "expires_at": [">", datetime.now()]})
            
            stats["levels"]["warm"] = {"active_entries": warm_count}
            stats["levels"]["cold"] = {"active_entries": cold_count}
            
            # Most accessed items
            popular_items = frappe.db.sql("""
                SELECT cache_key, cache_level, access_count 
                FROM `tabInsights Cache` 
                WHERE expires_at > NOW() 
                ORDER BY access_count DESC 
                LIMIT 10
            """, as_dict=True)
            
            stats["popular_items"] = popular_items
            
        except Exception as e:
            frappe.log_error(f"Cache stats error: {str(e)}")
            stats["levels"]["warm"] = {"status": "error"}
            stats["levels"]["cold"] = {"status": "error"}
        
        return stats


class SmartCacheKey:
    """Intelligent cache key generation for different data types"""
    
    @staticmethod
    def dashboard_key(dashboard_id: str, user_id: str, filters: Dict = None) -> str:
        """Generate cache key for dashboard data"""
        filter_hash = hashlib.md5(json.dumps(filters or {}, sort_keys=True).encode()).hexdigest()[:8]
        return f"dashboard:{dashboard_id}:{user_id}:{filter_hash}"
    
    @staticmethod  
    def query_key(query_hash: str, data_source: str, params: Dict = None) -> str:
        """Generate cache key for query results"""
        param_hash = hashlib.md5(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:8]
        return f"query:{data_source}:{query_hash}:{param_hash}"
    
    @staticmethod
    def ml_model_key(model_type: str, training_data_hash: str, params: Dict = None) -> str:
        """Generate cache key for ML model results"""
        param_hash = hashlib.md5(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:8]
        return f"ml:{model_type}:{training_data_hash}:{param_hash}"
    
    @staticmethod
    def ai_insight_key(query: str, context: Dict = None) -> str:
        """Generate cache key for AI-generated insights"""
        context_hash = hashlib.md5(json.dumps(context or {}, sort_keys=True).encode()).hexdigest()[:8]
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        return f"ai_insight:{query_hash}:{context_hash}"
    
    @staticmethod
    def erp_data_key(doctype: str, filters: Dict, fields: List[str]) -> str:
        """Generate cache key for ERPNext data queries"""
        filter_hash = hashlib.md5(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:8]
        field_hash = hashlib.md5(json.dumps(sorted(fields)).encode()).hexdigest()[:8]
        return f"erp:{doctype}:{filter_hash}:{field_hash}"


# Cache manager instance (lazy — no connections until first use)
cache_manager = CacheManager()


# Convenience functions for external use (synchronous)
def get_cached_data(key: str, cache_levels: List[str] = None) -> Optional[Any]:
    """Get cached data with automatic tier fallback"""
    levels = [_coerce_level(level) for level in cache_levels] if cache_levels else None
    return cache_manager.get(key, levels)


def cache_data(key: str, value: Any, level: str = "hot", ttl: Optional[int] = None, 
               metadata: Dict[str, Any] = None) -> bool:
    """Cache data in specified tier"""
    cache_level = _coerce_level(level)
    return cache_manager.set(key, value, cache_level, ttl, metadata)


def invalidate_cache(key: str, levels: List[str] = None):
    """Remove data from cache tiers"""
    cache_levels = [_coerce_level(level) for level in levels] if levels else None
    cache_manager.delete(key, cache_levels)


def get_cache_statistics() -> Dict[str, Any]:
    """Get comprehensive cache performance statistics"""
    return cache_manager.get_cache_stats()


# Decorator for automatic caching (synchronous)
def cached_result(cache_level: str = "hot", ttl: Optional[int] = None, 
                 key_generator: callable = None):
    """Decorator for automatic function result caching"""
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                # Default key generation
                key_data = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
                cache_key = hashlib.md5(key_data.encode()).hexdigest()
            
            # Try to get from cache
            cached = get_cached_data(cache_key)
            if cached is not None:
                return cached
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_data(cache_key, result, cache_level, ttl)
            
            return result
        
        return wrapper
    return decorator


# Background cache maintenance
def maintain_cache():
    """Background maintenance task for cache optimization"""
    cache_manager.clear_expired()
    
    # Cache performance optimization
    stats = cache_manager.get_cache_stats()
    
    # Log cache performance for monitoring
    frappe.log_error(json.dumps(stats), "Cache Performance Stats")


# Scheduled task hook
def hourly_cache_maintenance():
    """Hourly cache maintenance (called by scheduler)"""
    maintain_cache()