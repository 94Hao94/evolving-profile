import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import controller


def test_controller_contract_has_explicit_bounded_graph_budget():
    plan = {
        "primary_shape": "inventory",
        "coverage_dimensions": ["subjects", "sources"],
        "graph_route": {"enabled": True},
        "contextual_intent": {"resolved_subjects": [{"id": "person:wife", "name": "老婆", "aliases": ["婷婷"]}]},
        "project_state": {"project_key": "family-profile", "task_id": "audit-family"},
    }
    value = controller.build_retrieval_contract("老婆的全部历史资料和关系", plan)
    assert value["graph_budget"]["max_hops"] == 2
    assert value["graph_budget"]["max_nodes"] <= 120
    assert value["graph_budget"]["max_candidates"] <= 20
    assert value["subjects"][0]["id"] == "person:wife"


def test_controller_evidence_quality_escalates_nonzero_thin_result():
    plan = {"primary_shape": "inventory", "coverage_dimensions": ["subjects", "sources"],
            "contextual_intent": {"resolved_subjects": ["老婆", "优优"]}}
    contract = controller.build_retrieval_contract("老婆和优优的全部资料", plan)
    value = controller.evaluate_evidence_quality(
        contract["query"], [{"id": "a", "text": "老婆的一条记录", "scores": {"final": 0.8}}], contract
    )
    assert value["needs_escalation"] is True
    assert value["recommended_route"] == "research"


def test_short_two_character_chinese_subjects_are_valid_graph_anchors():
    assert controller._usable_entity_form("老婆") is True
    assert controller._usable_entity_form("优优") is True
    assert controller.build_graph_seed_queries("老婆和优优的全部资料与关系", 3)[:2] == ["老婆", "优优"]
