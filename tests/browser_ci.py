from __future__ import annotations

import argparse
import sys
import tempfile
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
    temporary = tempfile.TemporaryDirectory()
    deck = Path(temporary.name) / "deck.md"
    deck.write_text("## Browser test {.layout-1}\n\nInitial content.\n", encoding="utf-8")
    server = create_server(deck, "127.0.0.1", 0)
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
        base = f"http://127.0.0.1:{server.server_port}"
        driver.get(base)
        WebDriverWait(driver, 30).until(
            lambda active_driver: active_driver.find_element(By.ID, "save-state").text == "Saved"
        )
        incoming = deck.with_suffix(".incoming")
        incoming.write_text("## External reload {.layout-1}\n\nChanged outside Quarkfoil.\n", encoding="utf-8")
        incoming.replace(deck)
        WebDriverWait(driver, 10).until(
            lambda active_driver: "External reload" in active_driver.find_element(By.ID, "slide-list").text
        )
        driver.find_element(By.CSS_SELECTOR, '[data-mode="source"]').click()
        source_editor = driver.find_element(By.ID, "source-editor")
        driver.execute_script(
            "arguments[0].value += '\\nBrowser-only draft.\\n'; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            source_editor,
        )
        incoming.write_text("## External conflict {.layout-1}\n\nA second external revision.\n", encoding="utf-8")
        incoming.replace(deck)
        banner = WebDriverWait(driver, 10).until(
            lambda active_driver: active_driver.find_element(By.ID, "external-change-banner")
            if active_driver.find_element(By.ID, "external-change-banner").is_displayed() else False
        )
        if not driver.find_element(By.ID, "save-button").get_attribute("disabled"):
            raise RuntimeError("External deck conflict did not block browser saving")
        driver.execute_script(
            "arguments[0].value += '\\nContinued local edit.\\n'; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            source_editor,
        )
        if not driver.find_element(By.ID, "save-button").get_attribute("disabled"):
            raise RuntimeError("Editing after an external conflict re-enabled browser saving")
        banner.find_element(By.ID, "external-change-review").click()
        WebDriverWait(driver, 5).until(
            lambda active_driver: active_driver.find_element(By.ID, "external-change-dialog").get_attribute("open") is not None
        )
        if "Browser-only draft" not in driver.find_element(By.ID, "external-browser-source").get_attribute("value"):
            raise RuntimeError("External comparison omitted the browser draft")
        if "External conflict" not in driver.find_element(By.ID, "external-disk-source").get_attribute("value"):
            raise RuntimeError("External comparison omitted the disk revision")
        driver.find_element(By.ID, "external-use-disk").click()
        WebDriverWait(driver, 5).until(
            lambda active_driver: "External conflict" in active_driver.find_element(By.ID, "slide-list").text
            and not active_driver.find_element(By.ID, "external-change-banner").is_displayed()
        )
        invalid = "## Invalid one {#duplicate .layout-1}\n\n---\n\n## Invalid two {#duplicate .layout-1}\n"
        incoming.write_text(invalid, encoding="utf-8")
        incoming.replace(deck)
        WebDriverWait(driver, 10).until(
            lambda active_driver: "invalid" in active_driver.find_element(By.ID, "external-change-message").text.lower()
            and active_driver.find_element(By.ID, "external-change-banner").is_displayed()
        )
        if "External conflict" not in driver.find_element(By.ID, "slide-list").text:
            raise RuntimeError("Invalid external Markdown replaced the last valid presentation")
        driver.find_element(By.ID, "external-change-review").click()
        if not driver.find_element(By.ID, "external-use-disk").get_attribute("disabled"):
            raise RuntimeError("Invalid external Markdown remained directly loadable")
        summary = results.rsplit("\n", 1)[-1]
        print(f"Quarkfoil browser self-test passed in {browser}: {summary}; external editing passed")
        return 0
    finally:
        if driver is not None:
            driver.quit()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
