"""Black-box visual and semantic smoke check for the owner status page."""
from pathlib import Path
from playwright.sync_api import sync_playwright


OUT = Path("/Users/example/Documents/Codex/2026-07-11/ag/artifacts/hindsight-phase6-closeout-20260829/status-9998-visual.png")


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    try:
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto("http://127.0.0.1:9998/", wait_until="domcontentloaded", timeout=10_000)
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            # The dashboard deliberately polls /api/status; its continuous polling
            # means browser-wide network-idle never persists.  The rendered status
            # element below is the authoritative ready signal.
            pass
        page.screenshot(path=str(OUT), full_page=True)
        page.wait_for_selector("#health", timeout=10_000)
        assert page.locator("#health").inner_text() == "全链路正常"
        history = page.locator("#traceList").inner_text()
        assert "当前任务需要补齐相关历史事实" not in history
        assert not errors, errors
    finally:
        browser.close()
