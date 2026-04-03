#!/usr/bin/env python3
"""
CLI tool to show current Cognitive Evolution Metrics (Phase 5C).
"""
import sys
import os

# Ensure src is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.services.evolution_metrics import EvolutionMetrics

def main():
    metrics = EvolutionMetrics()
    report = metrics.generate_report()
    print(report)

if __name__ == "__main__":
    main()
