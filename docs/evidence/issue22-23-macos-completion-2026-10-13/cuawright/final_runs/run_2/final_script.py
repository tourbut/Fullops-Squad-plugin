import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:57186/healthy"
ROOT = Path(__file__).parent
SHOTS = ROOT / "screenshots"
LOG = ROOT / "final_script_log.txt"


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


async def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    pw = await async_playwright().start()
    browser = None
    try:
        browser = await pw.firefox.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 1800})
        await page.goto(URL)
        log("step 1 action: click Dark theme control")
        await page.get_by_role("button", name="Dark theme").click()
        await page.screenshot(path=str(SHOTS / "final_execution_1_dark_theme.png"))
        log("step 2 action: fill New todo with milk and click Add once")
        await page.get_by_role("textbox", name="New todo").fill("milk")
        await page.get_by_role("button", name="Add").click()
        await page.screenshot(path=str(SHOTS / "final_execution_2_add_milk.png"))
        log("step 3 action: click milk checkbox once")
        cb = page.locator("#list li").filter(has_text="milk").get_by_role("checkbox")
        await cb.click()
        await page.screenshot(path=str(SHOTS / "final_execution_3_milk_checked.png"))
        theme = await page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
            " || document.body.getAttribute('data-theme')"
            " || (document.documentElement.classList.contains('dark') || document.body.classList.contains('dark') ? 'dark' : (document.documentElement.className || document.body.className || ''))"
        )
        submits = await page.evaluate("window.submits")
        rows = await page.locator("#list li").count()
        checked = await cb.is_checked()
        log(
            f"FINAL_RESPONSE theme={theme} submits={submits} "
            f"list_li={rows} checkbox.checked={checked}"
        )
        await page.screenshot(path=str(SHOTS / "final_execution_4_final_state.png"))
    finally:
        if browser is not None:
            await browser.close()
        await pw.stop()


asyncio.run(main())
