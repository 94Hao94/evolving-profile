#!/usr/bin/env python3
"""Visually verify source-scope review details at desktop and mobile sizes."""

from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright


BANK = "personal-memory"
BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:10001"
FIXTURE = {
    "schema": "evolving-profile.runtime.v1",
    "context": {
        "status": "ready",
        "sessionCount": 1,
        "projectCount": 0,
        "graph": {
            "nodes": [
                {
                    "id": "session:thread-1",
                    "type": "session",
                    "label": "thread-1",
                    "status": "model_reviewed",
                    "reviewScope": "conversation_only_not_external_fact_verification",
                    "sourceMessageCount": 160,
                    "manualSourceCoverage": {
                        "scopeVerdict": "whole_session_scope_acceptable",
                        "reviewedSourceMessageCount": 160,
                        "episodeScopeVerdict": "single_coherent_task",
                    },
                    "summary": {
                        "compact": "对象：测试项目\n任务：检查摘要",
                        "standard": "对象：测试项目\n任务：检查摘要\n关键约束：保留来源",
                        "full": "对象：测试项目\n任务：检查摘要\n来源消息：160条",
                    },
                    "summaryBudget": {},
                    "sourceIds": ["rollout-summary.md"],
                },
                {"id": "bank:record-1", "type": "bank_world", "label": "record-1"},
            ],
            "edges": [{
                "source": "session:thread-1",
                "target": "bank:record-1",
                "type": "session_supports_bank_record",
            }],
            "timeline": [],
            "bankRecordLinks": {
                "available": True,
                "linked": 1,
                "reason": "isolated browser fixture",
            },
        },
    },
}


def assert_no_horizontal_overflow(page, label: str) -> None:
    widths = page.evaluate("""() => ({ scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth })""")
    assert widths["scroll"] <= widths["client"], f"{label}: horizontal overflow {widths}"


def main() -> None:
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.set_default_timeout(10_000)
        http_errors: list[str] = []
        console_errors: list[str] = []
        page.on("response", lambda response: http_errors.append(
            f"{response.status} {response.url}") if response.status >= 400 else None)
        page.on("console", lambda message: console_errors.append(
            message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("**/api/banks", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"banks": [{"bank_id": BANK, "name": "Scope review fixture"}]}, ensure_ascii=False)))
        page.route("**/api/version", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"features": {}})))
        page.route("**/api/evolving-profile/runtime*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(FIXTURE, ensure_ascii=False),
        ))

        response = page.goto(f"{BASE}/zh-CN/banks/{BANK}?view=data&subTab=context")
        page.wait_for_load_state("domcontentloaded")
        if page.get_by_text("情景摘要可视化", exact=True).count() == 0:
            print("HTTP", response.status if response else None, "URL", page.url)
            print(page.locator("body").inner_text()[:1800])
            page.screenshot(path="/tmp/ep-context-scope-review-failure.png", full_page=True)
        page.get_by_text("情景摘要可视化", exact=True).wait_for()
        page.get_by_role("button", name="表格", exact=True).click()
        source_button = page.get_by_role("button", name="查看来源节点 session:thread-1")
        source_button.click()
        page.get_by_text("全会话已复核").wait_for()
        page.get_by_text("160/160 条消息").wait_for()
        page.get_by_text("单一连贯任务").wait_for()
        assert_no_horizontal_overflow(page, "desktop scope details")
        page.screenshot(path="/tmp/ep-context-scope-review-desktop.png", full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        source_button.click()
        page.get_by_text("160/160 条消息").wait_for()
        assert_no_horizontal_overflow(page, "mobile scope details")
        page.screenshot(path="/tmp/ep-context-scope-review-mobile.png", full_page=True)

        FIXTURE["context"]["graph"]["nodes"][0].pop("manualSourceCoverage")
        page.set_viewport_size({"width": 1440, "height": 960})
        page.reload()
        page.get_by_text("情景摘要可视化", exact=True).wait_for()
        page.get_by_role("button", name="表格", exact=True).click()
        page.get_by_role("button", name="查看来源节点 session:thread-1").click()
        page.get_by_text("未记录", exact=True).wait_for()
        assert page.get_by_text("160/160 条消息").count() == 0

        browser.close()
    print("HTTP_ERRORS", http_errors)
    print("CONSOLE_ERRORS", console_errors)
    assert not page_errors, "\n".join(page_errors)
    assert not http_errors, "\n".join(http_errors)
    assert not console_errors, "\n".join(console_errors)
    print("context scope review visual check: passed")


if __name__ == "__main__":
    main()
