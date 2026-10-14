"""Visit each Streamlit Community Cloud app listed in apps.txt.

A real browser session counts as traffic, which resets the inactivity timer.
If an app is already asleep, the script clicks the wake button and waits
for the app to finish booting. Exits with code 1 if any app fails to load,
so GitHub sends a failure notification.
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

APPS_FILE = Path(__file__).parent / "apps.txt"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
WAKE_BUTTON_TEXT = "Yes, get this app back up!"
BOOT_TIMEOUT_S = 240      # cold starts can take a few minutes
STAY_ON_PAGE_S = 20       # keep the session open so the visit registers


def load_urls():
    lines = APPS_FILE.read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def app_is_rendered(page):
    """Streamlit Cloud serves the app inside an iframe; check every frame."""
    for frame in page.frames:
        try:
            if frame.query_selector('[data-testid="stApp"]'):
                return True
        except Exception:
            continue
    return False


def visit(browser, url):
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    woke = False
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        try:
            button = page.get_by_role("button", name=WAKE_BUTTON_TEXT)
            button.wait_for(state="visible", timeout=10_000)
            button.click()
            woke = True
        except PWTimeout:
            pass  # app was already awake

        deadline = time.time() + BOOT_TIMEOUT_S
        while time.time() < deadline:
            if app_is_rendered(page):
                page.wait_for_timeout(STAY_ON_PAGE_S * 1000)
                return True, woke
            page.wait_for_timeout(5_000)

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        name = url.split("//")[-1].split(".")[0]
        page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"), full_page=True)
        return False, woke
    except Exception as exc:
        print(f"  error: {exc}")
        return False, woke
    finally:
        context.close()


def main():
    urls = load_urls()
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for url in urls:
            print(f"Visiting {url}")
            ok, woke = visit(browser, url)
            status = "OK" if ok else "FAILED"
            note = " (was asleep, woke it)" if woke else ""
            print(f"  {status}{note}")
            if not ok:
                failures.append(url)
        browser.close()

    print(f"\n{len(urls) - len(failures)}/{len(urls)} apps loaded.")
    if failures:
        print("Failed:\n  " + "\n  ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
