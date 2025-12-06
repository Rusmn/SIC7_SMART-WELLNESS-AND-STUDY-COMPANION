#!/usr/bin/env python3
"""Test script to verify emotion endpoints are registered."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from app.api.routes import router

    print("✓ Router imported successfully")
    print(f"\nTotal routes: {len(router.routes)}")

    # Find emotion routes
    emotion_routes = [
        (r.path, r.methods)
        for r in router.routes
        if 'emotion' in r.path
    ]

    if emotion_routes:
        print(f"\n✓ Found {len(emotion_routes)} emotion endpoint(s):")
        for path, methods in emotion_routes:
            print(f"  - {list(methods)[0]} {path}")
    else:
        print("\n✗ No emotion endpoints found!")
        print("\nAll available routes:")
        for r in router.routes:
            if hasattr(r, 'path') and hasattr(r, 'methods'):
                print(f"  - {list(r.methods)[0]} {r.path}")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()