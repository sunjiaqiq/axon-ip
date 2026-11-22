#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试后端启动"""
import sys
import os

print("Testing backend startup...")
print(f"Python: {sys.executable}")
print(f"Working directory: {os.getcwd()}")

try:
    print("\n[1/3] Testing imports...")
    import fastapi
    import uvicorn
    print("  [OK] FastAPI and Uvicorn imported")
    
    print("\n[2/3] Testing main.py import...")
    import main
    print("  [OK] main.py imported successfully")
    
    print("\n[3/3] Testing app object...")
    if hasattr(main, 'app'):
        print(f"  [OK] app object exists: {type(main.app)}")
    else:
        print("  [FAIL] app object not found!")
        sys.exit(1)
    
    print("\n[SUCCESS] All checks passed! Backend should be able to start.")
    print("\nTo start the backend, run:")
    print("  py -3 main.py")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

