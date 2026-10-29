#!/usr/bin/env python3
"""
check_standards.py - Unified Verification Tool

This tool runs all required project checks locally:
1. Unit Tests (pytest)
2. Security Scan (bandit)
3. docs/ Link Integrity (verify_docs_links)

Usage: python scripts/check_standards.py
"""

import subprocess
import sys
import os
import shlex

def run_command(name, command, cwd="."):
    print(f"\n[🚀 Running: {name}]")
    print("-" * 40)
    try:
        # SECURITY FIX: Use shlex.split() to safely parse command string
        # and remove shell=True to prevent command injection
        result = subprocess.run(
            shlex.split(command),
            check=True,
            text=True,
            cwd=cwd
        )
        print(f"✅ {name} passed.")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ {name} failed.")
        return False

def main():
    # Ensure we are in project root
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)

    checks = [
        ("Unit Tests", "pytest --cov=src --cov-report=term-missing tests/"),
        ("Security Scan", "python3 -m bandit -r src/ -ll"),
        ("Docs Link Integrity", "python3 .agent/skills/docs-maintainer/scripts/verify_docs_links.py")
    ]

    all_passed = True
    for name, cmd in checks:
        if not run_command(name, cmd):
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 ALL STANDARDS PASSED. READY TO SUBMIT!")
        sys.exit(0)
    else:
        print("⚠️ SOME CHECKS FAILED. PLEASE FIX BEFORE SUBMITTING.")
        sys.exit(1)

if __name__ == "__main__":
    main()
