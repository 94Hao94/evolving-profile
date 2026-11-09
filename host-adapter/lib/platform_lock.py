"""Load the single platform-lock implementation without requiring caller PYTHONPATH."""
import importlib.util
from pathlib import Path
import sys

_name='ep_platform_lock'
if _name not in sys.modules:
    _path=Path(__file__).resolve().parents[2]/'guidance/ep_platform_lock.py'
    _spec=importlib.util.spec_from_file_location(_name,_path)
    _module=importlib.util.module_from_spec(_spec)
    sys.modules[_name]=_module
    try:_spec.loader.exec_module(_module)
    except BaseException:
        sys.modules.pop(_name,None);raise
_shared=sys.modules[_name]
LOCK_SH,LOCK_EX,LOCK_NB,LOCK_UN=_shared.LOCK_SH,_shared.LOCK_EX,_shared.LOCK_NB,_shared.LOCK_UN
flock,file_lock,atomic_replace_bytes=_shared.flock,_shared.file_lock,_shared.atomic_replace_bytes
