"""Screenshot every dashboard page so the rendering can actually be inspected.

Streamlit renders client-side, so an HTTP 200 on the root URL proves only that the
server started. It says nothing about whether a chart threw, a legend overflowed,
or a metric rendered as NaN. These are exactly the failures that survive an import
test and then show up in front of an audience.
"""

import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8512"
OUT = pathlib.Path(__file__).resolve().parents[1] / "logs" / "render_check"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("0_overview", "/"),
    ("1_inflation", "/Inflation"),
    ("2_monetary", "/Monetary"),
    ("3_fiscal", "/Fiscal"),
    ("4_external", "/External"),
    ("5_growth", "/Growth"),
    ("6_labour_energy", "/Labour_and_Energy"),
    ("7_explorer", "/Series_Explorer"),
    ("8_catalog", "/Data_Catalog"),
]

problems: list[str] = []

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1200},
                            device_scale_factor=1.5)

    console: list[str] = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
            if m.type == "error" else None)

    # Console messages for failed subresources do not carry the URL, so the
    # request itself is recorded to tell an app bug from Streamlit's own
    # health/host-config probes, which 404 on every subpage of a multipage app.
    failed: list[str] = []
    page.on("response", lambda r: failed.append(f"{r.status} {r.url}")
            if r.status >= 400 else None)
    IGNORED_404 = ("_stcore/health", "_stcore/host-config")

    for name, path in PAGES:
        console.clear()
        failed.clear()
        page.goto(BASE + path, wait_until="networkidle", timeout=90_000)
        # Streamlit streams the script's output; wait for the spinner to clear
        # rather than for a fixed delay.
        try:
            page.wait_for_selector("[data-testid='stStatusWidget']",
                                   state="detached", timeout=60_000)
        except Exception:
            pass
        page.wait_for_timeout(6000)

        body = page.inner_text("body")

        # A Streamlit exception renders as visible text in the app rather than
        # failing the request, so the page body has to be read to catch it.
        for marker in ("Traceback", "StreamlitAPIException", "KeyError",
                       "ValueError", "AttributeError", "IndexError",
                       "SyntaxError", "ModuleNotFoundError", "ImportError",
                       "NameError", "TypeError", "ZeroDivisionError",
                       "This app has encountered an error"):
            if marker in body:
                snippet = re.sub(r"\s+", " ", body[body.index(marker):][:400])
                problems.append(f"[{name}] {marker} -> {snippet}")
                break

        # Whole-word matching only: substring checks fire on ordinary words, and
        # 'inf' inside 'inflation' flagged every page of a macro dashboard.
        for bad in (r"\bnan\b", r"\bNaN\b", r"None%", r"\$nan\b", r"\binf\b",
                    r"\bNone\b", r"\bnull\b"):
            for line in body.splitlines():
                if re.search(bad, line) and len(line) < 90:
                    problems.append(f"[{name}] suspicious value ({bad}): {line.strip()!r}")
                    break

        # A page that raised before drawing anything still returns 200 and still
        # screenshots cleanly, so absence of an error string is not evidence that
        # the page rendered. Assert positively that charts and text are present.
        charts = page.locator("svg.main-svg").count()
        if charts == 0 and name not in {"8_catalog"}:
            problems.append(f"[{name}] NO CHARTS RENDERED")
        if len(body) < 600:
            problems.append(f"[{name}] page body suspiciously short ({len(body)} chars)")

        # Plotly clips a legend entry that overruns the plot; the clipped text is
        # still in the DOM, so compare rendered legend text against its box width.
        for i in range(page.locator("g.legend text").count()):
            el = page.locator("g.legend text").nth(i)
            txt = (el.text_content() or "").strip()  # SVG text is not an HTMLElement
            if txt.endswith(("\u2026",)):
                continue
            box = el.bounding_box()
            if box and box["width"] > 330:
                problems.append(f"[{name}] wide legend entry may clip: {txt!r} ({box['width']:.0f}px)")

        # Streamlit resolves its own health/host-config probes against the current
        # page path on multipage apps, so these 404s appear on every subpage and
        # are unrelated to the app's own code.
        real_failed = [f for f in failed if not any(x in f for x in IGNORED_404)]
        if real_failed:
            problems.append(f"[{name}] failed requests: {real_failed[:3]}")
        # Only surface console errors that are not just the ignored 404s echoing.
        if console and len(console) > len(failed) - len(real_failed):
            problems.append(f"[{name}] console errors: {console[:2]}")

        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
        print(f"shot {name:18} bodylen={len(body):6} charts={charts}")

    browser.close()

print("\n=== PROBLEMS ===" if problems else "\n=== no problems detected ===")
for p in problems:
    print(" ", p[:300])
sys.exit(1 if problems else 0)
