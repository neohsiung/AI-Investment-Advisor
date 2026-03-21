---
name: environment-doctor
description: Diagnose local development environment issues (Python version, ABI compatibility)
---

# Environment Doctor Skill

This skill helps diagnose common issues in the local development environment, specifically focusing on Python version mismatches and binary incompatibilities (like Numpy/Pandas ABI issues).

## Usage

Run the following script to check your environment health:

```bash
python3 .agent/skills/environment-doctor/check_env.py
```

## Checks Performed

1.  **Python Version**: Verifies that the active Python version is **3.10+**.
2.  **Pip Version**: Checks if `pip` is up-to-date.
3.  **Binary Compatibility**:
    *   Imports `numpy` and `pandas`.
    *   Performs a simple operation to trigger any potential ABI mismatch errors (e.g., `ValueError: numpy.dtype size changed`).
4.  **Critical Dependencies**: Checks versions of `numpy`, `pandas`, `pydantic` against known good configurations.

## Troubleshooting

If the doctor reports issues:

*   **Python Version**: Install Python 3.10 via `brew install python@3.10` and ensure it's in your PATH.
*   **Binary Incompatibility**: Run `pip install --force-reinstall -r requirements.txt` to rebuild wheels against the current numpy version.
