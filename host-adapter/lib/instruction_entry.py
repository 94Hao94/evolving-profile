"""Shared versioned manual loader for colocated host adapters and MCP runtime."""
from pathlib import Path
import os
import sys

GUIDANCE_ROOT = Path(os.environ.get('EVOLVING_PROFILE_GUIDANCE_SRC') or Path(__file__).resolve().parents[2] / 'guidance')
sys.path.insert(0, str(GUIDANCE_ROOT))
from memory_usage_instructions import CORE_TEXT, VERSION, content_sha256, instruction_block, record


def instruction_receipt():
    return {
        'instruction_version': VERSION,
        'content_sha256': content_sha256(),
        'core_text': CORE_TEXT,
        'source_file': str(GUIDANCE_ROOT / 'memory_usage_instructions.py'),
        'stage': 'hook_context_prepared',
        'model_context_visibility': 'not_measured',
    }
