import subprocess
import sys
import os
import argparse

def run_step(name, command):
    print(f"[*] {name}...")
    # Add venv/bin to path for this command
    env = os.environ.copy()
    venv_bin = os.path.abspath("venv/bin")
    if os.path.isdir(venv_bin):
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    
    try:
        # Use shell=True for some complex commands or if binary is in venv
        result = subprocess.run(command, shell=True, capture_output=True, text=True, env=env)

        if result.returncode == 0:
            print(f"  [OK] {name}")
            return True
        else:
            print(f"  [FAIL] {name}")
            if result.stdout:
                print("--- STDOUT ---")
                print(result.stdout)
            if result.stderr:
                print("--- STDERR ---")
                print(result.stderr)
            return False
    except Exception as e:
        print(f"  [ERROR] {name}: {e}")
        return False

def get_changed_files():
    """Get list of changed and untracked files."""
    try:
        # Staged and unstaged changes
        cmd = "git status --porcelain"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        files = []
        for line in result.stdout.splitlines():
            if line.strip():
                # Status is first 2 chars, then space, then filename
                files.append(line[3:].strip())
        return files
    except Exception:
        return []

def map_files_to_tests(files):
    """Map source files to their corresponding test files."""
    test_files = set()
    critical_files = ["requirements.txt", "conftest.py", "pytest.ini", "setup.py"]
    
    force_full = False
    for f in files:
        if any(cf in f for cf in critical_files):
            force_full = True
            break
        
        if f.startswith("src/") and f.endswith(".py"):
            # Map src/a/b.py -> tests/unit/a/test_b.py
            rel_path = f[4:] # Remove 'src/'
            dir_name = os.path.dirname(rel_path)
            base_name = os.path.basename(rel_path)
            test_path = os.path.join("tests/unit", dir_name, f"test_{base_name}")
            if os.path.exists(test_path):
                test_files.add(test_path)
            else:
                # If specific test doesn't exist, run the directory's tests
                dir_test_path = os.path.join("tests/unit", dir_name)
                if os.path.exists(dir_test_path):
                    test_files.add(dir_test_path)
        
        if f.startswith("tests/") and f.endswith(".py"):
            test_files.add(f)
            
    return list(test_files), force_full

def main():
    parser = argparse.ArgumentParser(description="CI Pre-Commit Check (Optimized)")
    parser.add_argument("--full", action="store_true", help="Run full suite instead of incremental")
    args = parser.parse_args()

    # Use python3.10 to match project requirements
    python_cmd = "python3.10"
    
    changed_files = get_changed_files()
    relevant_tests, force_full = map_files_to_tests(changed_files)
    
    is_full = args.full or force_full
    
    # Check for xdist
    has_xdist = False
    try:
        import pytest_xdist
        has_xdist = True
    except ImportError:
        pass

    xdist_flag = "-n auto" if has_xdist else ""
    
    steps = []
    
    if is_full:
        print("[!] Running FULL CI suite")
        steps.append(("Run tests with coverage (Full)", f"{python_cmd} -m pytest {xdist_flag} --cov=src --cov-report=term-missing"))
        steps.append(("Security Scan (Bandit - Full)", f"{python_cmd} -m bandit -r src/"))
    elif not changed_files:
        print("[!] No changes detected. Skipping incremental tests.")
    else:
        print(f"[!] Running INCREMENTAL CI for {len(changed_files)} changed files")
        
        # Test step
        if relevant_tests:
            test_paths = " ".join(relevant_tests)
            steps.append(("Run relevant tests", f"{python_cmd} -m pytest {test_paths}"))
        else:
            print("  [SKIP] No relevant tests found for changes.")
            
        # Bandit step (only on changed src files)
        src_changes = [f for f in changed_files if f.startswith("src/") and f.endswith(".py")]
        if src_changes:
            bandit_paths = " ".join(src_changes)
            steps.append(("Security Scan (Bandit - Incremental)", f"{python_cmd} -m bandit {bandit_paths}"))
            
    # Always run wiki and licenses if relevant or in full mode
    if is_full or any(f.startswith("wiki/") for f in changed_files):
        steps.append(("Wiki Integrity Check", f"{python_cmd} .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py"))
    
    steps.append(("License Compliance Check", f"{python_cmd} -m piplicenses"))

    all_success = True
    for name, cmd in steps:
        if not run_step(name, cmd):
            all_success = False
            
    if all_success:
        print("\n[SUCCESS] All CI tests passed!")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some CI tests failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
