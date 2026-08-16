from __future__ import annotations

import argparse
import functools
import http.server
import sys
import threading
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


def parse_args() -> argparse.Namespace:
    default_browser = "edge" if sys.platform == "win32" else "safari" if sys.platform == "darwin" else "firefox"
    parser = argparse.ArgumentParser(description="Smoke-test a Quarkfoil static export")
    parser.add_argument("directory", type=Path, help="export directory containing index.html")
    parser.add_argument("--browser", choices=("edge", "firefox", "safari"), default=default_browser)
    return parser.parse_args()


def create_driver(browser: str) -> webdriver.Remote:
    if browser == "edge":
        options = webdriver.EdgeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,1200")
        return webdriver.Edge(options=options)
    if browser == "firefox":
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        options.add_argument("--width=1440")
        options.add_argument("--height=1200")
        return webdriver.Firefox(options=options)
    driver = webdriver.Safari()
    driver.set_window_size(1440, 1200)
    return driver


def main() -> int:
    args = parse_args()
    directory = args.directory.resolve()
    if not (directory / "index.html").is_file():
        raise FileNotFoundError(f"Static export has no index.html: {directory}")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    driver = None
    try:
        driver = create_driver(args.browser)
        driver.get(f"http://127.0.0.1:{server.server_port}/")

        def initialized(active_driver: webdriver.Remote) -> bool:
            loading = active_driver.find_elements(By.ID, "loading")
            return not loading or "player-error" in (loading[0].get_attribute("class") or "")

        try:
            WebDriverWait(driver, 30).until(initialized)
        except TimeoutException as error:
            raise RuntimeError("Static presentation did not finish loading") from error
        loading = driver.find_elements(By.ID, "loading")
        if loading:
            raise RuntimeError(loading[0].text or "Static presentation failed to initialize")

        slides = driver.find_elements(By.CSS_SELECTOR, ".slides > section")
        if not slides:
            raise RuntimeError("Static presentation rendered no slides")
        printable_slides = len(driver.find_elements(By.CSS_SELECTOR, ".slides section.scientific-slide"))
        for index in range(1, len(slides)):
            selector = f".slides > section:nth-child({index + 1}).present"
            for _ in range(50):
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_RIGHT)
                try:
                    WebDriverWait(driver, 0.2).until(
                        lambda active_driver, expected=selector: active_driver.find_elements(By.CSS_SELECTOR, expected)
                    )
                    break
                except TimeoutException:
                    continue
            else:
                raise RuntimeError(f"Static presentation did not navigate to slide {index + 1}")
        driver.get(f"http://127.0.0.1:{server.server_port}/?print-pdf")
        try:
            WebDriverWait(driver, 30).until(
                lambda active_driver: "reveal-print" in (
                    active_driver.find_element(By.TAG_NAME, "html").get_attribute("class") or ""
                ).split()
            )
        except TimeoutException as error:
            raise RuntimeError("Static presentation did not enter Reveal's PDF print mode") from error
        try:
            WebDriverWait(driver, 30).until(
                lambda active_driver: active_driver.find_elements(By.CSS_SELECTOR, ".pdf-page")
            )
        except TimeoutException as error:
            raise RuntimeError("Static presentation did not create PDF pages") from error
        pdf_pages = driver.find_elements(By.CSS_SELECTOR, ".pdf-page")
        if len(pdf_pages) != printable_slides:
            raise RuntimeError(f"Static presentation created {len(pdf_pages)} PDF pages for {printable_slides} slides")
        print(f"Static export loaded, navigated, and created {printable_slides} PDF pages in {args.browser}")
        return 0
    finally:
        if driver is not None:
            driver.quit()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
