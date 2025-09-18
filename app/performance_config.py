"""
Performance configuration for optimizing bulk operations.
"""

import os
from typing import Optional

class PerformanceConfig:
    """Configuration for performance optimizations"""
    
    # Disable heavy monitoring during bulk operations
    DISABLE_METRICS_FOR_BULK: bool = True
    
    # Disable thread metrics collection during bulk operations
    DISABLE_THREAD_METRICS_FOR_BULK: bool = True
    
    # Disable detailed logging during bulk operations
    MINIMAL_LOGGING_FOR_BULK: bool = True
    
    # Batch size for very large bulk operations
    BULK_BATCH_SIZE: int = 100
    
    @classmethod
    def is_bulk_operation(cls, request_path: str, method: str) -> bool:
        """Check if this is a bulk operation that should be optimized"""
        return (
            method == "POST" and 
            request_path == "/api/v2/portfolios"
        )
    
    @classmethod
    def should_skip_metrics(cls, request_path: str, method: str) -> bool:
        """Check if metrics should be skipped for this request"""
        return cls.DISABLE_METRICS_FOR_BULK and cls.is_bulk_operation(request_path, method)

performance_config = PerformanceConfig()