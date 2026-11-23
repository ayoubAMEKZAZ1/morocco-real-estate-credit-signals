#!/usr/bin/env python3
"""Build the quarterly panel, run the lead/lag and early-warning analysis, and write outputs/.

    python scripts/run_credit_signals.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from credit_signals.report import run  # noqa: E402

if __name__ == "__main__":
    res = run()
    print(res["signals"].round(2).to_string(index=False))
    print("\nWrote outputs/credit_signals_report.md and three figures.")
