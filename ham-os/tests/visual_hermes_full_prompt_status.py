"""Black-box 9998 acceptance check for a real Hermes Full-Prompt trace."""

from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:9998/"
OUT = Path("/tmp/hermes-full-prompt-status.png")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(600)
        cards = page.locator(".trace-item")
        selected = None
        for index in range(cards.count()):
            text = cards.nth(index).inner_text()
            if "hermes-hindsight-full-prompt-adapter" in text and "实际注入" in text:
                selected = cards.nth(index)
                break
        assert selected is not None, "a real Hermes Full-Prompt trace is not selectable"
        selected.click()
        page.wait_for_timeout(400)
        flow = page.locator("#flow").inner_text()
        assert "Hermes Adapter" in flow, flow[:2000]
        assert "实际注入" in flow and "条证据已写入本次 Packet" in flow, flow[:4000]
        full_prompt_node = page.locator("#flow [data-map-node='working-set']").first
        full_prompt_node.click()
        page.wait_for_timeout(150)
        dialog = page.locator("#nodeDialog")
        assert dialog.locator("text=原始 Prompt（用户实际输入）").count() >= 1
        assert dialog.locator("text=Full Prompt（交给 Hindsight 检索的完整问题）").count() >= 1
        assert dialog.get_by_text("基于当前会话消解", exact=False).count() >= 1
        page.keyboard.press("Escape")
        page.screenshot(path=str(OUT), full_page=False)
        assert not errors, errors
        print({"screenshot": str(OUT), "trace_cards": cards.count(), "page_errors": errors})
        browser.close()


if __name__ == "__main__":
    main()
