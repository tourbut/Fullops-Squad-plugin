import argparse
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# param  type  default                              notes
# url    str   http://127.0.0.1:57186/healthy       allowlist /healthy|/duplicate|/no-check|/no-theme
# todo   str   milk                                 has_text filter; capture exact row text
ALLOWED = (
    "http://127.0.0.1:57186/healthy",
    "http://127.0.0.1:57186/duplicate",
    "http://127.0.0.1:57186/no-check",
    "http://127.0.0.1:57186/no-theme",
)
ROOT = Path(__file__).parent
SHOTS = ROOT / "screenshots"
LOG = ROOT / "final_script_log.txt"


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


async def complete_todo(url: str, todo: str) -> None:
    """Select dark theme, add one todo and mark its checkbox complete.

    Args:
        url (str): Allowlisted loopback fixture URL. Default: http://127.0.0.1:57186/healthy.
        todo (str): Nonempty todo text entered once. Default: milk.

    Returns:
        None. Actual final observations are written to the action log.
    """
    if url not in ALLOWED or not todo.strip():
        raise ValueError("rejected fixture URL or empty todo")
    SHOTS.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    log(f"step 0 params: url={url} todo={todo}")
    pw = await async_playwright().start()
    browser = None
    try:
        browser = await pw.firefox.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 1800})
        page.set_default_timeout(20000)
        await page.goto(url)
        log("step 1 action: click Dark theme control")
        await page.get_by_role("button", name="Dark theme").click()
        await page.screenshot(path=str(SHOTS / "final_execution_1_dark_theme.png"))
        log("step 2 action: fill New todo and click Add once")
        await page.get_by_role("textbox", name="New todo").fill(todo)
        await page.get_by_role("button", name="Add").click()
        await page.screenshot(path=str(SHOTS / "final_execution_2_add_todo.png"))
        log("step 3 action: click first matching checkbox once")
        row = page.locator("#list li").filter(has_text=todo).first
        cb = row.get_by_role("checkbox")
        await cb.click()
        await page.screenshot(path=str(SHOTS / "final_execution_3_todo_checked.png"))
        theme = await page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
            " || document.body.getAttribute('data-theme')"
            " || (document.documentElement.classList.contains('dark') || document.body.classList.contains('dark') ? 'dark' : (document.documentElement.className || document.body.className || ''))"
        )
        submits = await page.evaluate("window.submits")
        rows = await page.locator("#list li").count()
        checked = await cb.is_checked()
        exact = (await row.inner_text()).strip()
        log(
            f"FINAL_RESPONSE theme={theme} submits={submits} "
            f"list_li={rows} checkbox.checked={checked} exact_text={exact}"
        )
        await page.screenshot(path=str(SHOTS / "final_execution_4_final_state.png"))
    finally:
        if browser is not None:
            await browser.close()
        await pw.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=complete_todo.__doc__.splitlines()[0])
    p.add_argument("--url", type=str, help="Allowlisted loopback fixture URL. Default: http://127.0.0.1:57186/healthy.", default="http://127.0.0.1:57186/healthy")
    p.add_argument("--todo", type=str, help="Nonempty todo text entered once. Default: milk.", default="milk")
    a = p.parse_args()
    if a.url not in ALLOWED:
        raise SystemExit("rejected url")
    asyncio.run(complete_todo(a.url, a.todo))
