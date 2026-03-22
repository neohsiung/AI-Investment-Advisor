import subprocess
import sys
import os

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
            print(result.stdout)
            print(result.stderr)
            return False
    except Exception as e:
        print(f"  [ERROR] {name}: {e}")
        return False

def main():
    # Use python3.10 to match project requirements
    steps = [
        ("Run tests with coverage", "python3.10 -m pytest --cov=src --cov-report=term-missing"),
        ("Security Scan (Bandit)", "python3.10 -m bandit -r src/"),
        ("Wiki Integrity Check (Flat-Linking)", "python3.10 .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py"),
        ("License Compliance Check", "python3.10 -m pip_licenses")
    ]


    
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
