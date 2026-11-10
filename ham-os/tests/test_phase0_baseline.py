import importlib.util
import json
from pathlib import Path

HOME=Path.home()
CONTROLLER=HOME/'.hindsight/query-controller/controller.py'
HOOKS=HOME/'.codex/hooks.json'

def load_controller():
    spec=importlib.util.spec_from_file_location('ham_live_controller',CONTROLLER)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def test_live_controller_is_localhost_transparent_proxy():
    m=load_controller()
    # 1.13.5 was the phase-0 floor, not a permanent product version.  Pinning
    # it made every legitimate controller repair fail the baseline suite.
    assert tuple(int(part) for part in m.VERSION.split('.')) >= (1,13,5)
    assert m.RECALL_PATH.pattern.endswith('memories/recall$')
    assert m.DEFAULT_CONTRACT == HOME/'.hindsight/memory-contract-v5.json'

def test_compact_resume_semantics_are_checkpoint_without_duplicate_network_recall():
    source=(HOME/'.hindsight/custom-codex/scripts/session_start.py').read_text(encoding='utf-8')
    assert 'checkpoint' in source.lower()
    # The current product decision is local checkpoint handoff; do not restore an obsolete second recall.
    assert 'recall_memory(' not in source

def test_five_codex_hook_entrypoints_exist_and_match_live_config():
    cfg=json.loads(HOOKS.read_text())['hooks']
    expected={'SessionStart':'session_start.py','UserPromptSubmit':'recall.py','PostToolUse':'post_tool_use.py','PreCompact':'pre_compact.py','Stop':'retain.py'}
    assert set(expected).issubset(cfg)
    for name,script in expected.items():
        command=cfg[name][0]['hooks'][0]['command']
        assert command.endswith(script+'"')

def test_controller_contract_exposes_deadline_and_concurrency():
    contract=json.loads((HOME/'.hindsight/memory-contract-v5.json').read_text())
    qc=contract['queryController']; runtime=contract['runtime']
    assert qc['globalReadLimit'] >= qc['readParallelism']
    assert qc['deadlineContract']['hookTimeoutSeconds'] >= qc['deadlineContract']['deepClientTimeoutSeconds']
    assert runtime['llmMaxConcurrent'] >= runtime['reflectMaxConcurrent']
