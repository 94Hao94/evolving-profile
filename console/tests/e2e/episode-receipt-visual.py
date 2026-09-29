from playwright.sync_api import sync_playwright


BASE = "http://localhost:10002/zh-CN/banks/personal-memory?view=flow"
SUMMARY = "标准层：项目乙预算已比较，要求保留税费口径。\n助手回复只表示会话记录，不是外部核验。"
PROMPT = {
    "prompt_id": "episode-visual-fixture",
    "at": "2026-09-27T13:00:00+08:00",
    "user_prompt": "查一下项目乙预算当时是怎么定的。",
    "source": "codex-userpromptsubmit",
    "memory_route_receipt": {
        "decision": "recall",
        "recommended_route": "recall",
        "reason": "历史证据已返回，并读取了单个 episode。",
        "tool_events": [{
            "tool": "read_scenario_summary",
            "at": "2026-09-27T13:00:20+08:00",
            "returned_count": 1,
            "scenario_ids": ["session:fixture-session"],
            "scenario_type": "episode",
            "scenario_tier": "standard",
            "scenario_episode_id": "episode:fixture-session:message-4",
            "scenario_episode_title": "项目乙预算",
            "scenario_summary_status": "current",
            "scenario_summary_text": SUMMARY,
        }],
    },
    "historical_audit": {"route": "agent_mcp_recall", "state": "observed", "mode": "candidate_discovery",
                         "candidate_count": 1, "returned_to_host_count": 1,
                         "items": [{"id": "memory-1", "type": "experience", "text": "项目乙历史记录"}]},
}


def install_api_fixtures(page):
    def handle(route):
        url = route.request.url
        if "/api/evolving-profile/guidance/prompts/episode-visual-fixture" in url:
            route.fulfill(json=PROMPT)
        elif "/api/evolving-profile/guidance/prompts" in url:
            route.fulfill(json={"items": [PROMPT], "has_more": False})
        elif "/api/evolving-profile/guidance/memory-map" in url:
            route.fulfill(json={"nodes": []})
        elif "/api/evolving-profile/guidance/memory-check" in url:
            route.fulfill(json={"decision": "agent_decides", "recommended_route": "agent_decides",
                                "reason": "fixture", "catalog_hints": []})
        elif url.endswith("/api/banks"):
            route.fulfill(json={"banks": [{"bank_id": "personal-memory"}]})
        elif url.endswith("/api/version"):
            route.fulfill(json={"api_version": "fixture", "features": {}})
        else:
            route.continue_()

    page.route("**/api/**", handle)


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        install_api_fixtures(page)
        page.goto(BASE, wait_until="networkidle")
        page.screenshot(path="/tmp/ep-episode-receipt-desktop-before.png", full_page=True)
        page.get_by_text("路径 B", exact=True).click()
        page.screenshot(path="/tmp/ep-episode-receipt-desktop-after-click.png", full_page=True)
        dialog = page.get_by_role("dialog")
        details = dialog.get_by_text("查看已读取情景内容 · standard", exact=True)
        if not details.is_visible():
            raise AssertionError("episode read receipt disclosure is missing")
        details.click()
        dialog.get_by_text("项目乙预算已比较，要求保留税费口径。", exact=False).wait_for(state="visible")
        page.screenshot(path="/tmp/ep-episode-receipt-desktop.png", full_page=True)
        desktop_overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")

        dialog.get_by_role("button", name="Close").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_text("路径 B", exact=True).click()
        mobile_dialog = page.get_by_role("dialog")
        mobile_dialog.get_by_text("查看已读取情景内容 · standard", exact=True).click()
        mobile_dialog.get_by_text("项目乙预算已比较，要求保留税费口径。", exact=False).wait_for(state="visible")
        box = mobile_dialog.bounding_box()
        width = page.evaluate("window.innerWidth")
        if box is None or box["x"] < 0 or box["x"] + box["width"] > width:
            raise AssertionError(f"dialog does not fit mobile viewport: box={box}, width={width}")
        page.screenshot(path="/tmp/ep-episode-receipt-mobile.png", full_page=True)
        mobile_overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        browser.close()

    if desktop_overflow or mobile_overflow:
        raise AssertionError(f"horizontal overflow: desktop={desktop_overflow}, mobile={mobile_overflow}")
    if errors:
        raise AssertionError("browser errors: " + " | ".join(errors))
    print("episode receipt rendered and expanded at desktop/mobile widths; no horizontal overflow or browser errors")


if __name__ == "__main__":
    main()
