#!/usr/bin/env python3
"""Detect dominant source language profile in a directory.

Usage:
    python3 detect_profile.py <dir>
    python3 detect_profile.py <dir> --json
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(__file__))
from root_claw import detect_dominant_extension

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if not args:
        print("Usage: python3 detect_profile.py <dir> [--json]")
        sys.exit(1)

    target = args[0]
    if not os.path.isdir(target):
        print(f"Error: not a directory: {target}")
        sys.exit(1)

    result = detect_dominant_extension(target)

    if "--json" in flags:
        print(json.dumps(result, indent=2))
    else:
        print(f"Profile:    {result['profile']}")
        print(f"Extensions: {' '.join(result['extensions'])}")
        print(f"Total files: {result['total']}")
        print(f"Counts:     {result['counts']}")
