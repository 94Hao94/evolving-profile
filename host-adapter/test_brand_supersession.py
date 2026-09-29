from lib.relevance import filter_superseded_brand_constraints


def test_current_evolving_profile_query_rejects_superseded_legacy_product_constraint():
    legacy = {
        "id": "legacy-rule",
        "text": "在基于原版 Hindsight 的产品迭代中，必须完整保留核心功能，严禁删减或替换为轻量原型。",
        "metadata": {},
    }
    kept, rejected = filter_superseded_brand_constraints("Evolving Profile 的当前多维度偏好如何组织？", [legacy])

    assert kept == []
    assert rejected[0]["metadata"]["_ccy_admission"]["decision"] == "rejected_superseded_brand_constraint"


def test_historical_brand_query_keeps_legacy_constraint_for_auditable_history():
    legacy = {"id": "legacy-rule", "text": "原版 Hindsight 必须完整保留核心功能", "metadata": {}}

    kept, rejected = filter_superseded_brand_constraints("原版 Hindsight 当时有哪些完整保留约束？", [legacy])

    assert kept == [legacy]
    assert rejected == []
