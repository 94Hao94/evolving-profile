#!/usr/bin/env python3
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ham.api import Api
from ham.worker import process
api=Api(); print(json.dumps(process(api),ensure_ascii=False))
