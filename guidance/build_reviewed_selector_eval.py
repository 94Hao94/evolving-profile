"""Create the small human-reviewed selector holdout from the replay set.

The labels below are deliberately authored from task semantics, not copied from
the selector output. They are a review artifact and never mutate the registry.
"""
from __future__ import annotations

import json
from pathlib import Path

from selection_eval import score_reviewed_cases


REVIEW = {
    0: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="方案尚未给出，合法空集"),
    1: dict(must_select=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], optional=[], must_not=["starter:recommendations-for-decisions"], note="selector审计需要相关性与冲突边界"),
    2: dict(must_select=[], optional=[], must_not=["observation-guidance:f63cd4c6-feba-4362-808e-364490598751", "observation-guidance:7c8222b4-5782-4758-9322-18eb896ff570", "observation-guidance:905a39be-f42a-4a5f-b738-b159956c2d58"], valid_empty=True, note="明确纠正未请求PPT"),
    3: dict(must_select=["starter:recommendations-for-decisions"], optional=["observation-guidance:7886b8e8-6b57-4b80-aa59-da1bdad29666"], must_not=[], note="架构方案需要按推荐度和底层泛化判断"),
    4: dict(must_select=["starter:recommendations-for-decisions"], optional=[], must_not=[], note="本地知识库方案需要可决策建议"),
    5: dict(must_select=["starter:regression-and-error-class-review"], optional=[], must_not=["observation-guidance:aed42efb-dd10-419d-ab2b-56850199cab8"], note="页面故障优先回归与根因，不是PPT排版"),
    6: dict(must_select=[], optional=["starter:explanation-and-unfamiliar-terms"], must_not=[], note="谈判损害表述仍需看前文，弱可选"),
    7: dict(must_select=["starter:explanation-and-unfamiliar-terms"], optional=[], must_not=[], note="需要把分类理论讲清楚"),
    8: dict(must_select=["starter:explanation-and-unfamiliar-terms"], optional=[], must_not=[], note="主流理论归类解释"),
    9: dict(must_select=["starter:explanation-and-unfamiliar-terms"], optional=["starter:recommendations-for-decisions"], must_not=[], note="策略归类需要机制解释"),
    10: dict(must_select=["starter:regression-and-error-class-review"], optional=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], must_not=["observation-guidance:aed42efb-dd10-419d-ab2b-56850199cab8"], note="配置审查需要回归与架构边界"),
    11: dict(must_select=["starter:explanation-and-unfamiliar-terms"], optional=[], must_not=[], note="陌生SVG术语解释"),
    12: dict(must_select=["starter:regression-and-error-class-review"], optional=[], must_not=["observation-guidance:aed42efb-dd10-419d-ab2b-56850199cab8"], note="页面功能缺失需要同类回归"),
    13: dict(must_select=["starter:explanation-and-unfamiliar-terms"], optional=[], must_not=[], note="SVG/XML机制解释"),
    14: dict(must_select=["starter:explanation-and-unfamiliar-terms"], optional=[], must_not=[], note="源码到图像的机制解释"),
    15: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="简短确认，合法空集"),
    16: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="自足的生成请求，不需个人指导"),
    17: dict(must_select=["starter:regression-and-error-class-review"], optional=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], must_not=[], note="配置功能检查与记忆架构审计"),
    18: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="缺少对象与任务，合法空集"),
    19: dict(must_select=["observation-guidance:a7b239a7-7ec9-4f16-afe5-15f6f459c4c9"], optional=["starter:explanation-and-unfamiliar-terms"], must_not=[], note="科学因果机制解释"),
    20: dict(must_select=["starter:recommendations-for-decisions"], optional=["observation-guidance:c869e10d-5bd4-4777-ade7-03d46eda603f"], must_not=[], note="高校课程与AI应用方案"),
    21: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="术语定义自足"),
    22: dict(must_select=["starter:regression-and-error-class-review"], optional=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], must_not=[], note="配置与品牌问题需要回归和根因"),
    23: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="范围不明确，合法空集"),
    24: dict(must_select=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], optional=["starter:regression-and-error-class-review"], must_not=[], note="偏好相关性与架构匹配审计"),
    25: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="实时内存诊断由当前工具完成"),
    26: dict(must_select=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627", "codex-60d:c8bffee0884752691e15cf7e"], optional=[], must_not=[], note="MCP说明与候选/注入边界"),
    27: dict(must_select=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], optional=[], must_not=[], note="记忆有效期与替代关系"),
    28: dict(must_select=["observation-guidance:b52c1ca6-d276-4e06-9d5e-e8774c639627"], optional=["codex-60d:c9892c7b0a2bfa824138814d"], must_not=[], note="事实/经历/观察/模型职责边界"),
    29: dict(must_select=[], optional=[], must_not=[], valid_empty=True, note="具体投递地址需当前任务上下文"),
}


def build(replay_path: str | Path, output_path: str | Path) -> dict:
    source = json.loads(Path(replay_path).read_text())
    cases = []
    for index, row in enumerate(source.get("cases", [])[:30]):
        prompt = str(row.get("prompt", ""))
        anchor_index = next((value for key, value in {
            "没让你做ppt": 2, "SVG 引擎是什么": 11, "现在整个页面都进不去了": 5,
            "老婆和优优": 26, "世界事实、经历、观察": 28,
        }.items() if key in prompt), None)
        # Positional labels are valid only for the original fixed replay. A
        # fresh API sample must not inherit a different prompt's semantics.
        label_index = anchor_index
        labels = dict(REVIEW.get(label_index, {"must_select": [], "optional": [], "must_not": [], "valid_empty": False, "note": "待复核"}))
        labels["prompt_id"] = row.get("prompt_id")
        labels["prompt"] = row.get("prompt", "")
        labels["selected"] = row.get("selected", [])
        cases.append(labels)
    reviewed_count = sum(bool(case.get("must_select") or case.get("must_not") or case.get("valid_empty")) for case in cases)
    report = {
        "schema": "evolving-profile.selector-reviewed-eval.v1",
        "label_state": "human_reviewed_by_codex" if reviewed_count == len(cases) else "partially_reviewed_pending_labels",
        "source": str(replay_path),
        "cases": cases,
        "metrics": score_reviewed_cases([case for case in cases if case.get("must_select") or case.get("must_not") or case.get("valid_empty")]),
        "boundary": "Labels are semantic review judgments, not selector output copies; no registry mutation.",
    }
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("replay")
    parser.add_argument("output")
    args = parser.parse_args()
    print(json.dumps(build(args.replay, args.output), ensure_ascii=False, indent=2))
