"""Production import bridge for the Evolving Profile retrieval contract."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_SOURCE = Path(os.environ.get('EVOLVING_PROFILE_RETRIEVAL_QUALITY_SOURCE', str(Path.home() / '.evolving-profile/guidance-v1/retrieval_quality.py')))
_SPEC = importlib.util.spec_from_file_location('evolving_profile_retrieval_quality', _SOURCE)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f'cannot load retrieval quality source: {_SOURCE}')
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

build_retrieval_contract = _MODULE.build_retrieval_contract
evaluate_evidence_quality = _MODULE.evaluate_evidence_quality
project_record_index = _MODULE.project_record_index
