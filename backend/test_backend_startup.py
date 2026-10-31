#!/usr/bin/env python
"""
Test backend startup and imports
"""
import sys
import traceback

print("Testing backend imports...")
print("-" * 60)

tests = [
    ("outfit_compatibility_transformer", "from app.ml import outfit_compatibility_transformer"),
    ("preference_reward_model", "from app.ml import preference_reward_model"),
    ("preference_dataset", "from app.ml import preference_dataset"),
    ("recommendation_agent", "from app.agents import recommendation_agent"),
    ("app.main", "from app.main import app"),
]

failed = []

for name, import_stmt in tests:
    try:
        exec(import_stmt)
        print(f"[OK] {name}")
    except Exception as e:
        print(f"[ERROR] {name}: {str(e)[:100]}")
        failed.append((name, e))
        traceback.print_exc()
        print()

print("-" * 60)

if not failed:
    print("SUCCESS: All imports OK - Backend should start")
    sys.exit(0)
else:
    print(f"FAILED: {len(failed)} import error(s)")
    for name, error in failed:
        print(f"  - {name}: {error}")
    sys.exit(1)
