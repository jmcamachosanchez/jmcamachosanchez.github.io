#!/usr/bin/env python3
"""Update Crossref citation counts in publications.qmd.

Run this before rendering or publishing the website to refresh the static
citation metrics shown on the Publications page.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PUBLICATIONS_QMD = Path("publications.qmd")
CROSSREF_API = "https://api.crossref.org/works/"

PUBLICATIONS = [
    {
        "doi": "10.1016/j.jfluidstructs.2026.104560",
        "title": "Self-adaptive elastic flaps with bending and torsion for 3D blunt body drag reduction",
    },
    {
        "doi": "10.1063/5.0275586",
        "title": "Experimental analysis of the role of base blowing geometry on three-dimensional blunt body wakes",
    },
    {
        "doi": "10.1103/PhysRevFluids.8.044605",
        "title": "Experimental study on the effect of adaptive flaps on the aerodynamics of an Ahmed body",
    },
    {
        "doi": "10.1016/j.jfluidstructs.2023.103854",
        "title": "Drag reduction on a blunt body by self-adaption of rear flexibly hinged flaps",
    },
]


def citation_label(count: int) -> str:
    noun = "citation" if count == 1 else "citations"
    return f"{count} Crossref {noun}"


def display_date(day: date) -> str:
    return f"{day.day} {day.strftime('%B %Y')}"


def fetch_crossref_count(doi: str, timeout: float) -> int:
    url = CROSSREF_API + quote(doi, safe="")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "jmcamachosanchez.github.io citation updater (https://jmcamachosanchez.github.io)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except URLError:
        payload = fetch_crossref_with_curl(url, timeout=timeout)

    message = payload.get("message", {})
    count = message.get("is-referenced-by-count")
    if not isinstance(count, int):
        raise ValueError(f"Crossref response for {doi} did not include an integer citation count")
    return count


def fetch_crossref_with_curl(url: str, timeout: float) -> dict:
    completed = subprocess.run(
        ["curl", "-fsSL", "--max-time", str(int(timeout)), url],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def build_summary(counts: dict[str, int], retrieved: date) -> str:
    total = sum(counts.values())
    most_cited = max(counts.values(), default=0)
    selected = len(counts)
    retrieved_text = display_date(retrieved)

    return f"""::: {{.citation-metrics}}
::: {{.metric-card}}
<span class="metric-value">{total}</span>
<span class="metric-label">Crossref citations</span>
:::

::: {{.metric-card}}
<span class="metric-value">{selected}</span>
<span class="metric-label">Selected journal papers</span>
:::

::: {{.metric-card}}
<span class="metric-value">{most_cited}</span>
<span class="metric-label">Most cited paper</span>
:::
:::

<p class="metrics-note">Citation counts are based on Crossref's public cited-by metadata for the selected journal papers. Retrieved on {retrieved_text}; counts may differ from Google Scholar or Scopus.</p>"""


def replace_between_markers(text: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(
        rf"({re.escape(start)})(.*?)({re.escape(end)})",
        flags=re.DOTALL,
    )
    updated, matches = pattern.subn(rf"\1\n{replacement}\n\3", text)
    if matches != 1:
        raise ValueError(f"Expected one block between markers {start!r} and {end!r}, found {matches}")
    return updated


def update_publications_qmd(counts: dict[str, int], retrieved: date) -> None:
    text = PUBLICATIONS_QMD.read_text(encoding="utf-8")
    text = replace_between_markers(
        text,
        "<!-- crossref-summary:start -->",
        "<!-- crossref-summary:end -->",
        build_summary(counts, retrieved),
    )

    for doi, count in counts.items():
        text = replace_between_markers(
            text,
            f"<!-- crossref-citation:{doi} -->",
            "<!-- crossref-citation:end -->",
            f'<span class="citation-count">{citation_label(count)}</span>',
        )

    PUBLICATIONS_QMD.write_text(text, encoding="utf-8")


def collect_counts(publications: Iterable[dict[str, str]], timeout: float) -> dict[str, int]:
    counts: dict[str, int] = {}
    for publication in publications:
        doi = publication["doi"]
        counts[doi] = fetch_crossref_count(doi, timeout=timeout)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Crossref citation metrics in publications.qmd.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Network timeout per DOI request in seconds.")
    args = parser.parse_args()

    if not PUBLICATIONS_QMD.exists():
        print(f"Could not find {PUBLICATIONS_QMD}", file=sys.stderr)
        return 1

    try:
        counts = collect_counts(PUBLICATIONS, timeout=args.timeout)
        update_publications_qmd(counts, retrieved=date.today())
    except (HTTPError, URLError, TimeoutError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"Could not update Crossref metrics: {exc}", file=sys.stderr)
        return 1

    total = sum(counts.values())
    print(f"Updated Crossref citation metrics for {len(counts)} publications ({total} total citations).")
    for publication in PUBLICATIONS:
        doi = publication["doi"]
        print(f"- {citation_label(counts[doi])}: {publication['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
