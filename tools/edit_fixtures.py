"""Refresh the expected results in app/edit-fixtures.json from the editor itself.

The editor's parser.js is the reference for slide edits. Each fixture names a
source deck, an operation, and a slide; this tool runs that operation through
parser.js in a headless browser and rewrites the expected text (or marks the
case as refused). tests/test_deck_cli.py then holds the deck CLI to the same
results, and app/modules/selftest.js holds parser.js to them.

Run after deliberately changing trashSlide or restoreSlide, or after adding a
case (give it a name, operation, slide, and source):
    uv run python tools/edit_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scientific_slides.browser import browser_candidates, open_first_page, wait_for  # noqa: E402
from scientific_slides.exporter import serve_directory  # noqa: E402

APP = ROOT / "app"
FIXTURES = APP / "edit-fixtures.json"
OPERATIONS = {"trash": "trashSlide", "restore": "restoreSlide"}


def editor_results(fixtures: list[dict]) -> list[dict]:
    cases = [[OPERATIONS[fixture["operation"]], fixture["source"], fixture["slide"]] for fixture in fixtures]
    with serve_directory(APP) as origin, open_first_page(browser_candidates()) as (page, _):
        page.navigate(f"{origin}/index.html")
        wait_for(page, "document.readyState === 'complete'", 60)
        page.evaluate(f"""import('{origin}/modules/parser.js').then(parser => {{
          window.__editResults = {json.dumps(cases)}.map(([name, source, slide]) => {{
            try {{ return {{ expected: parser[name](parser.parseDeck(source), slide - 1) }}; }}
            catch (error) {{ return {{ error: true }}; }}
          }});
        }}).catch(error => {{ window.__editResults = "error:" + error.message; }})""")
        return wait_for(page, "window.__editResults", 60)


def main() -> int:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    refreshed = []
    for fixture, result in zip(fixtures, editor_results(fixtures)):
        entry = {key: fixture[key] for key in ("name", "operation", "slide", "source")}
        entry.update(result)
        refreshed.append(entry)
    FIXTURES.write_bytes((json.dumps(refreshed, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    changed = sum(old != new for old, new in zip(fixtures, refreshed))
    print(f"Refreshed {len(refreshed)} fixtures from parser.js; {changed} changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
