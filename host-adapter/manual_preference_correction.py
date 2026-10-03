"""Local Console entrypoint. Request comes through stdin."""
import json
import sys
from pathlib import Path
from lib.preference_correction import correct_preference

if __name__ == '__main__':
    config = json.loads(Path(sys.argv[1]).read_text())
    try:
        print(json.dumps(correct_preference(config['registry'], json.load(sys.stdin)), ensure_ascii=False))
    except (ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
