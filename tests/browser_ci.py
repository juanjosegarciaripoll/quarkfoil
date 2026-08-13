from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
    deck.write_text(
        "---\ntitle: Browser title test\n---\n\n"
        "## Browser test {.layout-1}\n\nInitial content.\n\n"
        "::: overlay {#markdown-test type=\"markdown\" x=\"55\" y=\"20\" w=\"30\" h=\"15\"}\nEditable overlay.\n:::\n\n"
        "::: overlay {#link-test type=\"citation\" key=\"test-link\" display=\"brief\" x=\"10\" y=\"70\" w=\"40\" h=\"8\"}\n:::\n",
        encoding="utf-8",
    )
    (Path(temporary.name) / "references.bib").write_text(
        "@misc{test-link, author={Tester, Alice}, year={2026}, url={about:blank#quarkfoil-attribution}}\n",
        encoding="utf-8",
    )
    server = create_server(deck, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    driver = None
    try:
        driver = create_driver(browser)
        driver.get(f"http://127.0.0.1:{server.server_port}/selftest.html")
        try:
            WebDriverWait(driver, 30).until(
                lambda active_driver: active_driver.find_element(By.TAG_NAME, "body").get_attribute("data-status")
                in {"passed", "failed"}
            )
        except TimeoutException as error:
            status = driver.find_element(By.TAG_NAME, "body").get_attribute("data-status")
            results = driver.find_element(By.ID, "results").text
            module_error = driver.execute_async_script(
                "const done = arguments[0]; import('/modules/selftest.js')"
                ".then(() => done('module loaded')).catch(error => done(error.stack || String(error)));"
            )
            screenshot = ROOT / "tests" / f"browser-{browser}-timeout.png"
            driver.save_screenshot(str(screenshot))
            raise RuntimeError(
                f"Browser self-test timed out in {browser} with status {status!r}:\n"
                f"{results[-4000:]}\nModule result: {module_error}\nScreenshot: {screenshot}"
            ) from error
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
        if driver.title != "Browser title test":
            raise RuntimeError(f"Browser title does not identify the slide deck: {driver.title!r}")
        driver.find_element(By.CSS_SELECTOR, '[data-mode="source"]').click()
        source_editor = driver.find_element(By.ID, "source-editor")
        original_source = source_editor.get_attribute("value")
        source_editor.send_keys(Keys.END, "Native source undo")
        source_editor.send_keys(Keys.CONTROL, "z")
        if source_editor.get_attribute("value") != original_source:
            raise RuntimeError("Ctrl+Z in the Source textarea did not use native text undo")
        driver.find_element(By.CSS_SELECTOR, '[data-mode="design"]').click()
        driver.execute_script(
            "document.querySelector('.overlay-markdown').dispatchEvent(new MouseEvent('click', {bubbles:true}));"
        )
        driver.execute_script(
            "document.querySelector('.overlay-markdown').dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));"
        )
        content_dialog = driver.find_element(By.ID, "content-dialog")
        WebDriverWait(driver, 5).until(lambda active_driver: content_dialog.get_attribute("open") is not None)
        content_editor = driver.find_element(By.ID, "content-editor")
        original_content = content_editor.get_attribute("value")
        content_editor.send_keys(Keys.END, "Native dialog undo")
        content_editor.send_keys(Keys.CONTROL, "z")
        if content_editor.get_attribute("value") != original_content:
            raise RuntimeError("Ctrl+Z in the content textarea did not use native text undo")
        content_editor.send_keys(Keys.ESCAPE)
        position = driver.find_element(By.ID, "prop-x")
        position.send_keys(Keys.CONTROL, "a")
        position.send_keys("25", Keys.ENTER)
        WebDriverWait(driver, 5).until(
            lambda active_driver: 'x="25"' in active_driver.find_element(By.ID, "source-editor").get_attribute("value")
        )
        driver.find_element(By.ID, "prop-text-color").click()
        WebDriverWait(driver, 5).until(
            lambda active_driver: active_driver.find_element(By.ID, "color-dialog").get_attribute("open") is not None
        )
        backdrop = driver.execute_script(
            "return getComputedStyle(document.querySelector('#color-dialog'), '::backdrop').backgroundColor;"
        )
        if backdrop not in {"rgba(0, 0, 0, 0)", "transparent"}:
            raise RuntimeError(f"Color dialog unexpectedly dims the slide with backdrop {backdrop}")
        driver.execute_script("document.querySelector('#color-dialog-value').value = '#123456';")
        driver.find_element(By.CSS_SELECTOR, "#color-dialog button[value='apply']").click()
        WebDriverWait(driver, 5).until(
            lambda active_driver: 'color="#123456"' in active_driver.find_element(By.ID, "source-editor").get_attribute("value")
        )
        original_window = driver.current_window_handle
        attribution_link = WebDriverWait(driver, 5).until(
            lambda active_driver: active_driver.find_element(By.CSS_SELECTOR, ".overlay-citation a[href]")
        )
        attribution_link.click()
        WebDriverWait(driver, 5).until(lambda active_driver: len(active_driver.window_handles) == 2)
        link_window = next(handle for handle in driver.window_handles if handle != original_window)
        driver.switch_to.window(link_window)
        WebDriverWait(driver, 5).until(lambda active_driver: "quarkfoil-attribution" in active_driver.current_url)
        driver.close()
        driver.switch_to.window(original_window)
        bibliography_path = Path(temporary.name) / "references.bib"
        bibliography_path.write_text(
            "@misc{test-link, author={Tester, Alice}, year={2030}, url={about:blank#quarkfoil-attribution}}\n",
            encoding="utf-8",
        )
        driver.find_element(By.CSS_SELECTOR, '[data-mode="source"]').click()
        citation_editor = driver.find_element(By.ID, "source-editor")
        driver.execute_script("arguments[0].setSelectionRange(arguments[0].value.length, arguments[0].value.length);", citation_editor)
        driver.find_element(By.ID, "bibliography-button").click()
        bibliography_dialog = driver.find_element(By.ID, "bibliography-dialog")
        WebDriverWait(driver, 5).until(lambda active_driver: bibliography_dialog.get_attribute("open") is not None)
        bibliography_source = driver.find_element(By.ID, "bibliography-source")
        if "2030" not in bibliography_source.get_attribute("value"):
            raise RuntimeError("Opening Bibliography did not reload an externally changed shared file")
        driver.execute_script(
            "arguments[0].value = arguments[0].value.replace('2030', '2027'); arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            bibliography_source,
        )
        driver.find_element(By.CSS_SELECTOR, ".bibliography-entry button").click()
        WebDriverWait(driver, 5).until(lambda active_driver: bibliography_dialog.get_attribute("open") is None)
        WebDriverWait(driver, 5).until(lambda active_driver: "2027" in bibliography_path.read_text(encoding="utf-8"))
        if "[@test-link]" not in citation_editor.get_attribute("value"):
            raise RuntimeError("Inline citation insertion did not use and save the current bibliography draft")
        driver.find_element(By.ID, "bibliography-button").click()
        WebDriverWait(driver, 5).until(lambda active_driver: bibliography_dialog.get_attribute("open") is not None)
        bibliography_source = driver.find_element(By.ID, "bibliography-source")
        driver.execute_script(
            "arguments[0].value = '@article{broken'; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            bibliography_source,
        )
        driver.find_element(By.ID, "bibliography-close").click()
        WebDriverWait(driver, 5).until(lambda active_driver: "Invalid BibTeX" in active_driver.find_element(By.ID, "bibliography-status").text)
        if bibliography_dialog.get_attribute("open") is None:
            raise RuntimeError("Invalid bibliography draft closed instead of reporting the save error")
        driver.execute_script(
            "arguments[0].value = arguments[1].replace('2027', '2028'); arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            bibliography_source,
            bibliography_path.read_text(encoding="utf-8"),
        )
        if driver.find_elements(By.ID, "bibliography-save"):
            raise RuntimeError("Bibliography dialog still exposes a separate Save action")
        driver.find_element(By.ID, "bibliography-close").click()
        WebDriverWait(driver, 5).until(lambda active_driver: bibliography_dialog.get_attribute("open") is None)
        WebDriverWait(driver, 5).until(lambda active_driver: "2028" in bibliography_path.read_text(encoding="utf-8"))
        driver.find_element(By.CSS_SELECTOR, '[data-mode="source"]').click()
        normalization_editor = driver.find_element(By.ID, "source-editor")
        messy_source = (
            "## Browser test {.layout-1}\n\n\n\n"
            "First paragraph.\n\n\n\nSecond paragraph.\n\n\n\n"
            "::: right\nUnused panel\n:::\n\n\n\n"
            "::: overlay {#preserved type=\"markdown\"}\nFirst overlay line\n\n\nSecond overlay line\n:::\n"
        )
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            normalization_editor,
            messy_source,
        )
        WebDriverWait(driver, 5).until(
            lambda active_driver: not active_driver.find_element(By.ID, "save-button").get_attribute("disabled")
        )
        driver.find_element(By.ID, "save-button").click()
        WebDriverWait(driver, 10).until(
            lambda active_driver: active_driver.find_element(By.ID, "save-state").text == "Saved"
        )
        saved_source = deck.read_text(encoding="utf-8")
        if "Unused panel" in saved_source or "First paragraph.\n\nSecond paragraph." not in saved_source:
            raise RuntimeError("Saving did not normalize top-level presentation content")
        if "First overlay line\n\n\nSecond overlay line" not in saved_source:
            raise RuntimeError("Saving changed whitespace inside an overlay")
        incoming = deck.with_suffix(".incoming")
        bibliography_path.write_text(
            "@misc{external-reference, author={External, Editor}, year={2031}}\n",
            encoding="utf-8",
        )
        incoming.write_text(
            "## External reload {.layout-1}\n\nChanged outside Quarkfoil [@external-reference].\n",
            encoding="utf-8",
        )
        incoming.replace(deck)
        WebDriverWait(driver, 10).until(
            lambda active_driver: "External reload" in active_driver.find_element(By.ID, "slide-list").text
        )
        WebDriverWait(driver, 10).until(
            lambda active_driver: active_driver.execute_script(
                "return Boolean(document.querySelector('#slides .citation')) "
                "&& !document.querySelector('#slides .citation-missing');"
            )
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
