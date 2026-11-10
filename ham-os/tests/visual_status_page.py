from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:9998/"
OUT = Path("/tmp/hindsight-bplus-status-page.png")
# The production-equivalence suite deliberately creates more than the 9998
# sidebar's recent-window size.  Select a fresh complex trace that is guaranteed
# to remain visible after the suite, instead of relying on the oldest case.
TARGETS = (
    "你测试的真实吗",
)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(800)
        assert page.locator("text=本次实际执行链路").count() >= 1
        cards = page.locator(".trace-item")
        selected = None
        for index in range(cards.count()):
            text = cards.nth(index).inner_text()
            if any(target in text for target in TARGETS) and "codex-hook" in text:
                selected = cards.nth(index)
                break
        assert selected is not None, "the fresh real Hook replay trace is not selectable"
        selected.click()
        page.wait_for_timeout(400)
        assert "你测试的真实吗" in selected.inner_text()
        # The history canvas can be arbitrarily tall; viewport capture is the
        # relevant interaction check and avoids turning a healthy UI test into
        # a browser-wide full-page layout crawl.
        page.screenshot(path=str(OUT), full_page=False)
        receipt_count = page.locator("[data-claim-delivery='v1']").count()
        if receipt_count < 1:
            print({
                "selected": selected.inner_text(),
                "detail": page.locator("#flow").inner_text()[:2000],
                "errors": errors,
                "renderers": page.evaluate("""() => ({
                    effectiveness: String(window.effectivenessItemsHtml || ''),
                    actual: String(window.actualView || ''),
                    terminalLoaded: !!document.getElementById('v40-claim-delivery-receipt-terminal'),
                    selectedId: window.selectedId,
                    selectedEffectiveness: ((window.data || {}).traces || []).find(t => t.query_id === window.selectedId)?.memory_effectiveness || {}
                })"""),
            })
        assert receipt_count >= 1
        assert page.locator("text=实际交付命题").count() >= 1
        full_prompt_node = page.locator("#flow [data-map-node='working-set']").first
        assert full_prompt_node.count() == 1, "the Full Prompt node is missing"
        full_prompt_node.click()
        page.wait_for_timeout(150)
        assert page.locator("#nodeDialog[open]").count() == 1
        assert page.locator("#nodeDialog").get_by_text("会话证据包", exact=False).count() >= 1
        assert page.locator("#nodeDialog").get_by_text("不会混入其他任务会话", exact=False).count() >= 1
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        output_node = page.locator("#flow [data-map-node='output']").first
        assert output_node.count() == 1, "the actual injection node is missing from the selected execution trace"
        output_node.click()
        page.wait_for_timeout(150)
        assert page.locator("#nodeDialog[open]").count() == 1
        assert page.locator("#nodeDialog [data-claim-delivery='v1']").count() >= 1
        assert page.locator("#nodeDialog").get_by_text("实际交付命题", exact=False).count() >= 1
        assert not errors, errors
        print({"screenshot": str(OUT), "trace_cards": cards.count(), "page_errors": errors})
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
