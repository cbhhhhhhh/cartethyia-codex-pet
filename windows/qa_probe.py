import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(sys.argv[1]).resolve() / "src")]
from qa_account import probe

raise SystemExit(0 if probe() else 1)
