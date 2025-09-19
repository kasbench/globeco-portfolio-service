"""
Validation caching system with LRU cache for portfolio operations.

This module provides high-performance validation caching to optimize
bulk operations and reduce redundant validation overhead.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from functools import lru_cache
from collections import OrderedDict
from datetime import datetime, UTC
import re
import threading
import time
from dataclasses import dataclass, field
from app.schemas import PortfolioPostDTO
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0
    cache_size: int = 0
    hit_rate: float = 0.0
    
    def update_hit_rate(self) -> None:
        """Update the hit rate calculation."""
        if self.total_requests > 0:
            self.hit_rate = self.hits / self.total_requests
        else:
            self.hit_rate = 0.0


class ValidationCache:
    """
    LRU cache for portfolio validation operations with configurable size and monitoring.
    
    Provides caching for:
    - Portfolio name format validation
    - Database existence checks
    - Validation results for performance optimization
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize validation cache with configurable size.
        
        Args:
            max_size: Maximum number of entries to cache (default: 1000)
        """
        self.max_size = max_size
        self._name_format_cache: OrderedDict[str, bool] = OrderedDict()
        self._existence_cache: OrderedDict[str, bool] = OrderedDict()
        self._batch_validation_cache: OrderedDict[str, bool] = OrderedDict()
        self._stats = CacheStats()
        self._lock = threading.RLock()
        
        # Compile regex pattern once for name format validation
        self._name_pattern = re.compile(r'^[a-zA-Z0-9\s\-_]+$')
        
        logger.info(f"ValidationCache initialized with max_size={max_size}")
    
    def _evict_lru(self, cache: OrderedDict) -> None:
        """
        Evict least recently used item from cache if at capacity.
        
        Args:
            cache: The cache dictionary to evict from
        """
        if len(cache) >= self.max_size:
            evicted_key = cache.popitem(last=False)[0]  # Remove oldest item
            self._stats.evictions += 1
            logger.debug(f"Evicted LRU cache entry: {evicted_key}")
    
    def _move_to_end(self, cache: OrderedDict, key: str) -> None:
        """
        Move key to end of OrderedDict to mark as most recently used.
        
        Args:
            cache: The cache dictionary
            key: The key to move to end
        """
        cache.move_to_end(key)
    
    def is_valid_name_format_cached(self, name: str) -> bool:
        """
        Cached validation for portfolio name format.
        
        Validates:
        - 1-200 characters
        - Alphanumeric, spaces, hyphens, and underscores only
        
        Args:
            name: Portfolio name to validate
            
        Returns:
            True if name format is valid, False otherwise
        """
        if not name:
            return False
        
        with self._lock:
            self._stats.total_requests += 1
            
            # Check cache first
            if name in self._name_format_cache:
                self._stats.hits += 1
                self._move_to_end(self._name_format_cache, name)
                result = self._name_format_cache[name]
                logger.debug(f"Name format validation cache HIT: {name} -> {result}")
                return result
            
            # Cache miss - perform validation
            self._stats.misses += 1
            
            # Validate name format
            is_valid = (
                1 <= len(name) <= 200 and
                bool(self._name_pattern.match(name))
            )
            
            # Cache the result
            self._evict_lru(self._name_format_cache)
            self._name_format_cache[name] = is_valid
            self._stats.cache_size = len(self._name_format_cache)
            
            logger.debug(f"Name format validation cache MISS: {name} -> {is_valid}")
            return is_valid
    
    def is_portfolio_exists_cached(self, name: str, exists: bool) -> None:
        """
        Cache the existence check result for a portfolio name.
        
        Args:
            name: Portfolio name
            exists: Whether the portfolio exists in database
        """
        if not name:
            return
        
        normalized_name = name.strip().lower()
        
        with self._lock:
            self._evict_lru(self._existence_cache)
            self._existence_cache[normalized_name] = exists
            logger.debug(f"Cached portfolio existence: {normalized_name} -> {exists}")
    
    def get_cached_existence(self, name: str) -> Optional[bool]:
        """
        Get cached existence result for a portfolio name.
        
        Args:
            name: Portfolio name to check
            
        Returns:
            True if exists, False if not exists, None if not cached
        """
        if not name:
            return None
        
        normalized_name = name.strip().lower()
        
        with self._lock:
            if normalized_name in self._existence_cache:
                self._move_to_end(self._existence_cache, normalized_name)
                result = self._existence_cache[normalized_name]
                logger.debug(f"Portfolio existence cache HIT: {normalized_name} -> {result}")
                return result
            
            logger.debug(f"Portfolio existence cache MISS: {normalized_name}")
            return None
    
    def cache_batch_validation_result(self, batch_key: str, is_valid: bool) -> None:
        """
        Cache the result of batch validation.
        
        Args:
            batch_key: Unique key representing the batch (e.g., hash of names)
            is_valid: Whether the batch validation passed
        """
        with self._lock:
            self._evict_lru(self._batch_validation_cache)
            self._batch_validation_cache[batch_key] = is_valid
            logger.debug(f"Cached batch validation: {batch_key} -> {is_valid}")
    
    def get_cached_batch_validation(self, batch_key: str) -> Optional[bool]:
        """
        Get cached batch validation result.
        
        Args:
            batch_key: Unique key representing the batch
            
        Returns:
            True if valid, False if invalid, None if not cached
        """
        with self._lock:
            if batch_key in self._batch_validation_cache:
                self._move_to_end(self._batch_validation_cache, batch_key)
                result = self._batch_validation_cache[batch_key]
                logger.debug(f"Batch validation cache HIT: {batch_key} -> {result}")
                return result
            
            logger.debug(f"Batch validation cache MISS: {batch_key}")
            return None
    
    def get_stats(self) -> CacheStats:
        """
        Get current cache statistics.
        
        Returns:
            CacheStats object with current performance metrics
        """
        with self._lock:
            self._stats.cache_size = (
                len(self._name_format_cache) + 
                len(self._existence_cache) + 
                len(self._batch_validation_cache)
            )
            self._stats.update_hit_rate()
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                total_requests=self._stats.total_requests,
                cache_size=self._stats.cache_size,
                hit_rate=self._stats.hit_rate
            )
    
    def clear_cache(self) -> None:
        """Clear all cached validation results."""
        with self._lock:
            self._name_format_cache.clear()
            self._existence_cache.clear()
            self._batch_validation_cache.clear()
            self._stats = CacheStats()
            logger.info("ValidationCache cleared")
    
    def clear_existence_cache(self) -> None:
        """Clear only the existence cache (useful when database changes)."""
        with self._lock:
            self._existence_cache.clear()
            logger.info("ValidationCache existence cache cleared")


# Global validation cache instance
_validation_cache: Optional[ValidationCache] = None
_cache_lock = threading.Lock()


def get_validation_cache(max_size: int = 1000) -> ValidationCache:
    """
    Get or create the global validation cache instance.
    
    Args:
        max_size: Maximum cache size (only used on first creation)
        
    Returns:
        ValidationCache instance
    """
    global _validation_cache
    
    if _validation_cache is None:
        with _cache_lock:
            if _validation_cache is None:
                _validation_cache = ValidationCache(max_size=max_size)
    
    return _validation_cache


def reset_validation_cache() -> None:
    """Reset the global validation cache instance (useful for testing)."""
    global _validation_cache
    
    with _cache_lock:
        if _validation_cache:
            _validation_cache.clear_cache()
        _validation_cache = None


# Cached validation functions for direct use
def is_valid_name_format(name: str) -> bool:
    """
    Cached validation for portfolio name format.
    
    Args:
        name: Portfolio name to validate
        
    Returns:
        True if name format is valid, False otherwise
    """
    cache = get_validation_cache()
    return cache.is_valid_name_format_cached(name)


def validate_portfolio_names_format(names: List[str]) -> Tuple[List[str], List[str]]:
    """
    Validate multiple portfolio names using cache for performance.
    
    Args:
        names: List of portfolio names to validate
        
    Returns:
        Tuple of (valid_names, invalid_names)
    """
    cache = get_validation_cache()
    valid_names = []
    invalid_names = []
    
    for name in names:
        if cache.is_valid_name_format_cached(name):
            valid_names.append(name)
        else:
            invalid_names.append(name)
    
    return valid_names, invalid_names


def generate_batch_key(portfolio_dtos: List[PortfolioPostDTO]) -> str:
    """
    Generate a unique key for batch validation caching.
    
    Args:
        portfolio_dtos: List of portfolio DTOs
        
    Returns:
        Unique string key representing the batch
    """
    # Create a hash-like key from sorted names and versions
    names_and_versions = [(dto.name.strip().lower(), dto.version or 1) for dto in portfolio_dtos]
    names_and_versions.sort()  # Sort for consistent key generation
    
    # Create a simple hash-like key
    key_parts = [f"{name}:{version}" for name, version in names_and_versions]
    batch_key = "|".join(key_parts)
    
    # Truncate if too long to avoid memory issues
    if len(batch_key) > 500:
        batch_key = batch_key[:500] + f"...({len(portfolio_dtos)})"
    
    return batch_key