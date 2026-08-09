"""Generate DATA_CATALOG.md from the source registry and observed series index.

Run from the repository root:
    python docs/generate_catalog.py

The generator deliberately reads rather than duplicates source attributes so the
human-readable catalog moves with config/sources.yaml.  Series counts and observed
ranges come from data/metadata/series_index.csv; an em dash means that the source
is registered but does not currently contribute a parsed series to the index.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.yaml"
INDEX = ROOT / "data" / "metadata" / "series_index.csv"
OUTPUT = ROOT / "docs" / "DATA_CATALOG.md"

THEME_ORDER = ["inflation", "monetary", "fiscal", "external", "growth", "labour", "energy"]
TIER_LABELS = {
    1: "Tier 1 — fully automated dashboard core",
    2: "Tier 2 — automated download and semi-structured parse",
    3: "Tier 3 — PDF/manual reference sources",
}


def clean(value: object) -> str:
    """Return a Markdown-table-safe scalar."""
    if value is None or value == "":
        return "—"
    return " ".join(str(value).replace("|", "\\|").split())


def link(url: object, label: str) -> str:
    """Render a known official URL, retaining the literal URL in the document."""
    if not url:
        return "—"
    text = str(url)
    return f"[{label}]({text})"


def observed_ranges() -> dict[str, dict[str, str]]:
    """Aggregate indexed series count and min/max date for each source id."""
    stats: dict[str, dict[str, str]] = {}
    with INDEX.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)
    for source_id, source_rows in by_source.items():
        starts = sorted(row["start"] for row in source_rows if row.get("start"))
        ends = sorted(row["end"] for row in source_rows if row.get("end"))
        stats[source_id] = {
            "series": str(len(source_rows)),
            "range": f"{starts[0]} to {ends[-1]}" if starts and ends else "—",
        }
    return stats


def main() -> None:
    registry = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    sources = registry["sources"]
    observed = observed_ranges()

    by_tier = Counter(int(source["tier"]) for source in sources)
    by_publisher = Counter(str(source["publisher"]).upper() for source in sources)

    lines = [
        "# Data Catalog",
        "",
        "This catalog is generated from `config/sources.yaml` and "
        "`data/metadata/series_index.csv`; do not edit it by hand. Regenerate with "
        "`python docs/generate_catalog.py` after changing the registry or ETL outputs.",
        "",
        "## Registry summary",
        "",
        f"- **Catalogued official sources:** {len(sources)}",
        f"- **Sources by tier:** Tier 1 — {by_tier[1]}; Tier 2 — {by_tier[2]}; Tier 3 — {by_tier[3]}",
        "- **Sources by publisher:** " + "; ".join(
            f"{publisher} — {count}" for publisher, count in sorted(by_publisher.items())
        ),
        "- **Observed-series fields:** `Series count` and `Observed range` are joined from the current series index. They describe parsed output, not necessarily the full historical coverage advertised by the publisher.",
        "",
        "## How to read it",
        "",
        "- **Official page** is the publisher landing page to cite in analysis.",
        "- **Direct URL** is a stable file/feed URL where one is registered. “Dynamic discovery” means the extractor resolves a current link from the publisher's listing; “manual” means no unattended retrieval path is configured.",
        "- **Parser** names the registered transformation function. A dash means the source is catalogued for research/reference but is not presently transformed into the master table.",
        "- **Configured coverage** is the registry's source-level description; it is not overwritten by the observed range.",
        "",
    ]

    sources_by_theme: dict[str, list[dict]] = defaultdict(list)
    for source in sources:
        sources_by_theme[str(source["theme"])].append(source)

    ordered_themes = THEME_ORDER + sorted(set(sources_by_theme) - set(THEME_ORDER))
    for theme in ordered_themes:
        theme_sources = sources_by_theme.get(theme, [])
        if not theme_sources:
            continue
        lines += [f"## {theme.title()}", ""]
        for tier in (1, 2, 3):
            group = sorted((s for s in theme_sources if int(s["tier"]) == tier), key=lambda s: s["id"])
            if not group:
                continue
            lines += [f"### {TIER_LABELS[tier]}", ""]
            lines += [
                "| ID | Name | Publisher | Format | Frequency | Configured coverage | Tier | Parser | Series count | Observed range | Official page | Direct URL |",
                "|---|---|---|---|---|---|---:|---|---:|---|---|---|",
            ]
            for source in group:
                observation = observed.get(source["id"], {"series": "—", "range": "—"})
                if source.get("url"):
                    direct = link(source["url"], "direct file/feed")
                elif source.get("discover"):
                    direct = f"Dynamic discovery: `{clean(source['discover'])}`"
                    if source.get("query"):
                        direct += f" (`{clean(source['query'])}`)"
                else:
                    direct = "Manual / not configured"
                lines.append(
                    "| " + " | ".join([
                        f"`{clean(source['id'])}`",
                        clean(source.get("name")),
                        clean(str(source.get("publisher", "")).upper()),
                        clean(source.get("fmt")),
                        clean(source.get("frequency")),
                        clean(source.get("coverage")),
                        clean(source.get("tier")),
                        f"`{clean(source.get('parser'))}`" if source.get("parser") else "—",
                        observation["series"],
                        observation["range"],
                        link(source.get("page"), "official page"),
                        direct,
                    ]) + " |"
                )
            lines.append("")

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(sources)} sources; {sum(1 for s in sources if s.get('parser'))} parser-wired).")


if __name__ == "__main__":
    main()
