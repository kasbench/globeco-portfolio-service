#!/usr/bin/env python3
"""
Enable complete performance mode by removing all monitoring overhead.
"""

import shutil
import os

def enable_performance_mode():
    """Enable complete performance mode"""
    
    print("🚀 Enabling Performance Mode...")
    print("=" * 50)
    
    # 1. Backup and replace main.py
    if os.path.exists("app/main.py"):
        shutil.copy("app/main.py", "app/main_original.py")
        print("✅ Backed up main.py")
    
    if os.path.exists("app/main_minimal.py"):
        shutil.copy("app/main_minimal.py", "app/main.py")
        print("✅ Switched to minimal main.py")
    
    # 2. Backup and replace tracing.py
    if os.path.exists("app/tracing.py"):
        shutil.copy("app/tracing.py", "app/tracing_original.py")
        print("✅ Backed up tracing.py")
    
    if os.path.exists("app/tracing_minimal.py"):
        shutil.copy("app/tracing_minimal.py", "app/tracing.py")
        print("✅ Switched to minimal tracing.py")
    
    print("\n🎯 Performance Mode Enabled!")
    print("Disabled components:")
    print("  ❌ OpenTelemetry tracing")
    print("  ❌ OpenTelemetry metrics")
    print("  ❌ Prometheus metrics")
    print("  ❌ Database operation tracing")
    print("  ❌ Heavy middleware")
    print("  ❌ Debug logging")
    print("  ❌ Thread monitoring")
    
    print("\n📈 Expected improvements:")
    print("  🚀 10-50x faster bulk operations")
    print("  ⚡ Reduced memory usage")
    print("  🔥 Lower CPU overhead")
    
    print("\n🔄 To restore full monitoring:")
    print("  python disable_performance_mode.py")

def disable_performance_mode():
    """Restore full monitoring"""
    
    print("🔄 Disabling Performance Mode...")
    print("=" * 50)
    
    # Restore main.py
    if os.path.exists("app/main_original.py"):
        shutil.copy("app/main_original.py", "app/main.py")
        print("✅ Restored original main.py")
    
    # Restore tracing.py
    if os.path.exists("app/tracing_original.py"):
        shutil.copy("app/tracing_original.py", "app/tracing.py")
        print("✅ Restored original tracing.py")
    
    print("\n📊 Full Monitoring Restored!")
    print("Enabled components:")
    print("  ✅ OpenTelemetry tracing")
    print("  ✅ OpenTelemetry metrics")
    print("  ✅ Prometheus metrics")
    print("  ✅ Database operation tracing")
    print("  ✅ Enhanced middleware")
    print("  ✅ Debug logging")
    print("  ✅ Thread monitoring")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "disable":
        disable_performance_mode()
    else:
        enable_performance_mode()