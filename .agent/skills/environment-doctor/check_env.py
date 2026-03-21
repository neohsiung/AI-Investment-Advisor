import sys
import importlib.metadata
import platform

def check_python_version():
    print(f"[*] Checking Python version... {platform.python_version()}")
    if sys.version_info < (3, 10):
        print("    [!] FAIL: Python 3.10+ is required.")
        return False
    print("    [+] PASS")
    return True

def check_binary_compatibility():
    print("[*] Checking Binary Compatibility (Numpy/Pandas)...")
    try:
        import numpy as np
        import pandas as pd
        
        # Trigger potential ABI issue
        df = pd.DataFrame({'a': [1, 2, 3]})
        _ = np.array(df['a'])
        
        print(f"    [+] PASS: Numpy {np.__version__}, Pandas {pd.__version__}")
        return True
    except Exception as e:
        print(f"    [!] FAIL: {e}")
        print("    -> Tip: Try 'pip install --force-reinstall pandas numpy'")
        return False

def main():
    print("=== Environment Doctor ===")
    checks = [
        check_python_version(),
        check_binary_compatibility()
    ]
    
    if all(checks):
        print("\n[+] Environment looks healthy!")
        sys.exit(0)
    else:
        print("\n[!] Issues detected. Please fix them before proceeding.")
        sys.exit(1)

if __name__ == "__main__":
    main()
