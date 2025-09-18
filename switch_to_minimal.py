#!/usr/bin/env python3
"""
Switch to minimal FastAPI app for performance testing.
"""

import shutil
import os

def switch_to_minimal():
    """Switch main.py to the minimal version"""
    
    # Backup original main.py
    if os.path.exists("app/main.py"):
        shutil.copy("app/main.py", "app/main_original.py")
        print("✅ Backed up original main.py to main_original.py")
    
    # Replace main.py with minimal version
    if os.path.exists("app/main_minimal.py"):
        shutil.copy("app/main_minimal.py", "app/main.py")
        print("✅ Switched to minimal main.py")
        
        print("\n🚀 Minimal FastAPI app activated!")
        print("Features disabled:")
        print("  - OpenTelemetry tracing")
        print("  - OpenTelemetry metrics")
        print("  - Prometheus metrics")
        print("  - Heavy middleware")
        print("  - Debug logging")
        
        print("\n📝 To restore original:")
        print("  python restore_original.py")
        
    else:
        print("❌ main_minimal.py not found!")

def restore_original():
    """Restore original main.py"""
    
    if os.path.exists("app/main_original.py"):
        shutil.copy("app/main_original.py", "app/main.py")
        print("✅ Restored original main.py")
        print("🔄 Full monitoring and tracing restored")
    else:
        print("❌ main_original.py backup not found!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_original()
    else:
        switch_to_minimal()