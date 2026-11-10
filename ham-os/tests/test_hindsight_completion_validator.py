import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "hindsight_completion_validator.py"
SPEC = ROOT / "HINDSIGHT-THREE-WAY-RECALL-VALIDATION-AND-REPAIR-SPEC-2026-08-30.md"


def load_validator():
    spec = importlib.util.spec_from_file_location("hindsight_completion_validator", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def evidence(tmp_path: Path, name: str) -> dict:
    path = tmp_path / name
    path.write_text(json.dumps({"name": name}), encoding="utf-8")
    return {
        "passed": True,
        "evidence_path": name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def passing_case(tmp_path: Path, case_id: str, category: str, split: str = "dev") -> dict:
    validator = load_validator()
    return {
        "id": case_id,
        "category": category,
        "split": split,
        "seams": {
            seam: evidence(tmp_path, f"{case_id}-{seam}.json")
            for seam in validator.REQUIRED_SEAMS
        },
        "metrics": {metric: True for metric in validator.REQUIRED_METRICS},
        "verification": {
            "same_case_replay_passed": True,
            "transfer_checks": [
                {"id": f"{case_id}-transfer-1", "passed": True},
                {"id": f"{case_id}-transfer-2", "passed": True},
            ],
            "negative_control": {"id": f"{case_id}-negative", "passed": True},
            "sealed_holdout": {"id": f"{case_id}-holdout", "passed": True},
        },
    }


def test_new_spec_is_independent_and_self_contained():
    text = SPEC.read_text(encoding="utf-8")
    assert "不属于、不修改、也不依赖" in text
    assert "A 路：Context＋Native Memory" in text
    assert "B 路：Bank Exhaustive" in text
    assert "C 路：Production Hindsight" in text
    assert "C-answer：Hindsight-only 回答" in text
    assert "不可跳过的红绿循环" in text
    assert "新会话接管步骤" in text


def test_validator_refuses_healthy_but_unevidenced_system():
    validator = load_validator()
    result = validator.evaluate({"cases": []})
    assert result["complete"] is False
    assert any("need 20" in reason for reason in result["failures"])


def test_validator_requires_three_independent_lanes_and_visual_seam():
    validator = load_validator()
    row = {
        "id": "handoff-1",
        "category": "cross_task_handoff",
        "seams": {
            "context_native_answer": {"passed": True},
            "hindsight_only_answer": {"passed": True},
        },
    }
    result = validator.evaluate({"cases": [row]})
    assert result["complete"] is False
    failure = "\n".join(result["failures"])
    assert "bank_exhaustive" in failure
    assert "production_recall" in failure
    assert "status_page_visual" in failure


def test_validator_rejects_case_missing_quality_or_anti_overfit_gates(tmp_path):
    validator = load_validator()
    row = passing_case(tmp_path, "history-1", "open_inventory")
    row["metrics"]["relation_closure_passed"] = False
    row["verification"]["transfer_checks"] = row["verification"]["transfer_checks"][:1]
    result = validator.evaluate({"cases": [row]}, evidence_root=tmp_path)
    failure = "\n".join(result["failures"])
    assert "relation_closure_passed" in failure
    assert "two passed transfer checks" in failure


def test_validator_checks_evidence_hashes(tmp_path):
    validator = load_validator()
    row = passing_case(tmp_path, "entity-1", "entity_relation")
    first = next(iter(row["seams"].values()))
    first["sha256"] = "0" * 64
    result = validator.evaluate({"cases": [row]}, evidence_root=tmp_path)
    assert any("sha256 mismatch" in reason for reason in result["failures"])


def test_validator_can_only_complete_full_diverse_suite(tmp_path):
    validator = load_validator()
    categories = sorted(validator.REQUIRED_DIVERSITY)
    cases = []
    for index in range(20):
        category = categories[index % len(categories)]
        split = "holdout" if index < 5 else ("transfer" if index < 10 else "dev")
        cases.append(passing_case(tmp_path, f"case-{index:02d}", category, split))
    manifest = {
        "cases": cases,
        "suite_gates": {gate: True for gate in validator.REQUIRED_SUITE_GATES},
    }
    result = validator.evaluate(manifest, evidence_root=tmp_path)
    assert result["complete"] is True
    assert result["passed_count"] == 20
    assert result["holdout_passed"] == 5
