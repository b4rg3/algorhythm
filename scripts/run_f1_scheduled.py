"""Entry point for the scheduled F1 run: no console window, output appended to logs/f1/runner.log."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.makedirs(os.path.join(ROOT, "logs", "f1"), exist_ok=True)

with open(os.path.join(ROOT, "logs", "f1", "runner.log"), "a", encoding="utf-8") as log:
    sys.stdout = sys.stderr = log
    import f1
    from rich.console import Console

    f1.console = Console(file=log, force_terminal=False, width=200)
    try:
        f1.run()
    except Exception as exc:  # last-resort logging; f1.run already logs per-coin errors
        print(f"FATAL: {exc!r}")
