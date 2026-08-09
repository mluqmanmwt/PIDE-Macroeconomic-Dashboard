"""Check that documentation URLs are already present in the approved research inputs."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT.parent / "research" / "source_catalog.md"
TARGETS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]

# URLs placed in the brief are duplicated in the research catalog or source
# registry for this repository. The matcher keeps punctuation outside a link out
# of the comparison, then uses exact string containment in the authoritative
# inputs to avoid accepting fabricated variants.
URL_RE = re.compile(r"https?://[^\s<>'\"`\])}]+")
TRAILING = ".,;:!?"


def urls(text: str) -> set[str]:
    return {match.group(0).rstrip(TRAILING) for match in URL_RE.finditer(text)}


def main() -> int:
    approved = (ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")
    approved += "\n" + RESEARCH.read_text(encoding="utf-8")
    documented: dict[Path, set[str]] = {path: urls(path.read_text(encoding="utf-8")) for path in TARGETS}
    all_urls = set().union(*documented.values())
    unknown = sorted(url for url in all_urls if url not in approved)

    report = [
        "# Link Consistency Check",
        "",
        "Approved corpus: `config/sources.yaml` and the mandatory source research catalogue.",
        f"Markdown files checked: {len(TARGETS)}",
        f"Unique documentation URLs: {len(all_urls)}",
        f"URLs not found in approved corpus: {len(unknown)}",
        "",
    ]
    if unknown:
        report += ["## Unmatched URLs", ""]
        report += [f"- `{url}`" for url in unknown]
    else:
        report += ["**PASS.** Every URL in the generated Markdown already appears in the approved source registry or research catalogue."]
    (ROOT / "docs" / "LINK_CONSISTENCY_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
