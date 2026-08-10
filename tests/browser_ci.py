from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from scientific_slides.server import create_server


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    default_browser = "edge" if sys.platform == "win32" else "firefox"
    parser = argparse.ArgumentParser(description="Run the Quarkfoil browser self-test")
    parser.add_argument(
        "--browser",
        choices=("edge", "firefox"),
        default=default_browser,
        help=f"browser engine to test (default: {default_browser})",
    )
    return parser.parse_args()


def create_driver(browser: str) -> webdriver.Remote:
    if browser == "edge":
        options = webdriver.EdgeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,1200")
        return webdriver.Edge(options=options)

    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")
    options.add_argument("--width=1440")
    options.add_argument("--height=1200")
    return webdriver.Firefox(options=options)


def main() -> int:
    browser = parse_args().browser
    server = create_server(ROOT / "example/deck.md", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    driver = None
    try:
        driver = create_driver(browser)
        driver.get(f"http://127.0.0.1:{server.server_port}/selftest.html")
        WebDriverWait(driver, 30).until(
            lambda active_driver: active_driver.find_element(By.TAG_NAME, "body").get_attribute("data-status")
            in {"passed", "failed"}
        )
        status = driver.find_element(By.TAG_NAME, "body").get_attribute("data-status")
        results = driver.find_element(By.ID, "results").text
        if status != "passed" or "checks passed" not in results:
            screenshot = ROOT / "tests" / f"browser-{browser}-failure.png"
            driver.save_screenshot(str(screenshot))
            raise RuntimeError(
                f"Browser self-test did not pass in {browser}:\n{results[-4000:]}\n"
                f"Screenshot: {screenshot}"
            )
        summary = results.rsplit("\n", 1)[-1]
        print(f"Quarkfoil browser self-test passed in {browser}: {summary}")
        return 0
    finally:
        if driver is not None:
            driver.quit()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
