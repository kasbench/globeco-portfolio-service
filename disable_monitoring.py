#!/usr/bin/env python3
"""
Script to temporarily disable heavy monitoring for performance testing.
"""

import os

def disable_monitoring():
    """Set environment variables to disable heavy monitoring"""
    
    # Disable metrics collection
    os.environ['ENABLE_METRICS'] = 'false'
    os.environ['METRICS_DEBUG_LOGGING'] = 'false'
    
    # Disable thread metrics
    os.environ['ENABLE_THREAD_METRICS'] = 'false'
    os.environ['THREAD_METRICS_DEBUG_LOGGING'] = 'false'
    
    # Disable OpenTelemetry metrics logging
    os.environ['OTEL_METRICS_LOGGING_ENABLED'] = 'false'
    
    # Set minimal log level
    os.environ['LOG_LEVEL'] = 'WARNING'
    
    print("✅ Monitoring disabled for performance testing")
    print("Environment variables set:")
    print("  ENABLE_METRICS=false")
    print("  METRICS_DEBUG_LOGGING=false") 
    print("  ENABLE_THREAD_METRICS=false")
    print("  THREAD_METRICS_DEBUG_LOGGING=false")
    print("  OTEL_METRICS_LOGGING_ENABLED=false")
    print("  LOG_LEVEL=WARNING")
    print("\nRestart your application to apply these changes.")

if __name__ == "__main__":
    disable_monitoring()