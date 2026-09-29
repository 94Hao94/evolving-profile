#!/usr/bin/env python3
"""Read-only UI regression checks against a running Evolving Profile console."""

from __future__ import annotations

import sys
import re
import json
import importlib.util
from pathlib import Path

from PIL import Image
from playwright.sync_api import Browser, Page, sync_playwright


BANK = "personal-memory"
BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:9999"
OUT = Path("output/playwright")
OUT.mkdir(parents=True, exist_ok=True)
USES_PRODUCTION_ORIGIN = BASE.startswith("http://127.0.0.1:9999")


def url(view: str, extra: str = "") -> str:
    return f"{BASE}/zh-CN/banks/{BANK}?view={view}{extra}"


def assert_no_page_overflow(page: Page, label: str) -> None:
    widths = page.evaluate("""() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth })""")
    assert widths["scroll"] <= widths["client"], f"{label}: horizontal overflow {widths}"


def wait_for_ready(page: Page) -> None:
    # The console keeps status requests alive, so `networkidle` can never be a
    # meaningful readiness signal. A rendered route root plus route-specific
    # assertions below proves the UI has completed its initial transition.
    page.wait_for_load_state("domcontentloaded")
    page.locator("main, [role=main], body").first.wait_for(state="visible")
    # Let route-owned requests settle before moving to the next route. Rapidly
    # destroying a page turns intentionally cancelled fetches into misleading
    # console noise that a normal settled page does not expose.
    page.wait_for_timeout(750)


def assert_fusion_is_centered(page: Page) -> None:
    fusion_button = page.get_by_role("button", name=re.compile(r"^融合心智模型\s+\d+$"))
    fusion_button.wait_for(state="visible")
    fusion_label = fusion_button.get_attribute("aria-label") or fusion_button.inner_text()
    count_match = re.search(r"(\d+)$", fusion_label.strip())
    assert count_match, f"fusion model count is missing: {fusion_label!r}"
    model_count = int(count_match.group(1))
    fusion_button.click()
    page.wait_for_timeout(250)
    legend_text = page.locator("aside").filter(has_text="颜色与数量").inner_text()
    print(f"fusion legend: {legend_text[:180]!r}", flush=True)
    assert re.search(r"当前视图：\s*融合心智模型", legend_text), "fusion selector did not update the legend"
    canvas = page.locator("canvas").first
    canvas.wait_for(state="visible")
    image_path = OUT / "fusion-centered.png"
    canvas.screenshot(path=str(image_path))

    image = Image.open(image_path).convert("RGB")
    points: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            r, g, b = image.getpixel((x, y))
            # Fusion nodes use the dedicated fuchsia color. Exclude gray UI,
            # white canvas, and the amber reasoning-dimension palette.
            if r > 120 and b > 100 and g < r * 0.8:
                points.append((x, y))
    if model_count == 0:
        assert not points, "empty fusion model set rendered colored nodes"
        return
    assert len(points) > 50, "fusion canvas has no visible model nodes"
    center_x = sum(x for x, _ in points) / len(points) / image.width
    center_y = sum(y for _, y in points) / len(points) / image.height
    assert 0.38 <= center_x <= 0.62, f"fusion graph shifted horizontally: {center_x:.3f}"
    assert 0.30 <= center_y <= 0.70, f"fusion graph shifted vertically: {center_y:.3f}"
    page.get_by_role("button", name=re.compile("全部显示")).click()
    assert re.search(r"当前视图：\s*全部显示", page.locator("aside").filter(has_text="颜色与数量").inner_text())


def audit_desktop(browser: Browser, errors: list[str]) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
    page.set_default_timeout(8_000)
    page.on("console", lambda message: errors.append(f"console:{message.type}:{message.text}") if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(f"pageerror:{error}"))

    page.goto(url("data", "&subTab=preferences"))
    print("desktop preferences", flush=True)
    wait_for_ready(page)
    page.get_by_role("heading", name="多维度偏好").wait_for()
    assert_fusion_is_centered(page)
    assert_no_page_overflow(page, "desktop preferences")
    page.screenshot(path=str(OUT / "preferences-desktop.png"), full_page=True)

    route_matrix = [
        ("data", "记忆"),
        ("recall", "Recall"),
        ("documents", "文档"),
        ("profile", "记忆库配置"),
    ]
    if USES_PRODUCTION_ORIGIN:
        route_matrix.insert(3, ("flow", "链路"))
    for view, heading in route_matrix:
        print(f"desktop {view}", flush=True)
        page.goto(url(view))
        wait_for_ready(page)
        page.get_by_role("heading", name=heading).first.wait_for()
        assert_no_page_overflow(page, f"desktop {view}")
        page.screenshot(path=str(OUT / f"{view}-desktop.png"), full_page=True)

    if USES_PRODUCTION_ORIGIN:
        page.goto(url("flow"))
        print("desktop flow interaction", flush=True)
        wait_for_ready(page)
        prompts = page.locator("button").filter(has_text=re.compile("入口已检查|observed_entry_adapter"))
        prompts.first.wait_for(state="visible")
        assert prompts.count() > 0, "flow page has no captured user prompt"
        prompts.nth(0).click()
        detail_heading = page.locator("h2").filter(has_text=re.compile("节点详情"))
        detail_heading.wait_for()
        before = detail_heading.inner_text()
        history = page.get_by_role("button", name=re.compile("Codex 按需历史读取|历史记录 · Hook 自动召回"))
        history.click()
        page.get_by_text("读取模式").wait_for()
        page.get_by_text("候选索引").wait_for()
        assert page.get_by_text("读取模式").count() > 0, "history node did not open the audit card"
        assert before, "flow detail heading is empty"
        page.get_by_role('button', name=re.compile('记忆使用说明书')).click()
        page.get_by_role('dialog').wait_for()
        page.keyboard.press('Escape')
        assert page.get_by_role('dialog').count() == 0

        # Isolated browser fixture: render the new receipt without writing
        # a synthetic user turn into the production ingress ledger.
        manual_path=Path(__file__).resolve().parents[3]/'guidance/memory_usage_instructions.py'
        spec=importlib.util.spec_from_file_location('manual_e2e', manual_path)
        manual=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manual)
        fixture={
            'prompt_id':'isolated-ui-fixture', 'at':'2026-09-17T09:00:00Z',
            'user_prompt':'隔离界面验收：解释一下这个机制',
            'instruction_receipt':{'instruction_version':manual.VERSION, 'content_sha256':manual.content_sha256(), 'core_text':manual.CORE_TEXT, 'source_file':str(manual_path), 'stage':'hook_context_prepared', 'model_context_visibility':'not_measured'},
            'guidance_receipt':{'host_state':'hook_context_prepared','guidance_items':[], 'model_sections':[], 'coverage':'complete_active_set'},
            'routes':{'historical_memory':'not_observed','entry_guidance':'observed_entry_adapter'},
        }
        page.route('**/api/evolving-profile/guidance/prompts**', lambda route: route.fulfill(status=200,content_type='application/json',body=json.dumps(fixture if '/prompts/' in route.request.url else {'items':[fixture],'has_more':False})))
        page.reload()
        page.get_by_role('button',name=re.compile('记忆使用说明书.*memory-use')).click()
        dialog=page.get_by_role('dialog')
        assert manual.CORE_TEXT in dialog.inner_text()
        assert manual.VERSION in dialog.inner_text()
        assert manual.content_sha256() in dialog.inner_text()
        page.screenshot(path=str(OUT/'entry-manual-fixture-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function("""() => {const d=document.querySelector('[role=dialog]'); if (!d) return false; const r=d.getBoundingClientRect(); return r.left>=0 && r.right<=window.innerWidth && d.scrollWidth<=d.clientWidth+1;}""")
        assert_no_page_overflow(page,'manual dialog mobile')
        page.screenshot(path=str(OUT/'entry-manual-fixture-mobile.png'),full_page=True)
        page.keyboard.press('Escape')
        assert page.get_by_role('dialog').count()==0
    page.close()


def audit_mobile(browser: Browser, errors: list[str]) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    page.set_default_timeout(8_000)
    page.on("console", lambda message: errors.append(f"mobile-console:{message.type}:{message.text}") if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(f"mobile-pageerror:{error}"))
    routes = [("data", "&subTab=preferences"), ("profile", ""), ("documents", ""), ("recall", "")]
    if USES_PRODUCTION_ORIGIN:
        routes.insert(1, ("flow", ""))
    for view, extra in routes:
        print(f"mobile {view}", flush=True)
        page.goto(url(view, extra))
        wait_for_ready(page)
        assert_no_page_overflow(page, f"mobile {view}")
        page.screenshot(path=str(OUT / f"{view}-mobile.png"), full_page=True)
    page.close()


def main() -> None:
    errors: list[str] = []
    with sync_playwright() as playwright:
        print("launch browser", flush=True)
        browser = playwright.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        audit_desktop(browser, errors)
        audit_mobile(browser, errors)
        browser.close()
    assert not errors, "\n".join(errors)
    print("console audit: passed")


if __name__ == "__main__":
    main()
