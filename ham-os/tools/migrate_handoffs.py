#!/usr/bin/env python3
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ham.api import Api
from ham.migrations import migrate
p=Path.home()/'.hindsight/codex/state/task-handoffs.json'; dry='--apply' not in sys.argv
print(json.dumps(migrate(Api().ledger,p,dry),ensure_ascii=False))
