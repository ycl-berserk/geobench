"""Download public GeoGebra materials as `.ggb` files.

Usage::

    python scripts/download_geogebra.py --profile https://www.geogebra.org/u/2641739553 --out corpus
    python scripts/download_geogebra.py --ids MJWHp9en ghjf7p7k --out corpus

A public material page carries the real file URL inside its embedded
JSON, URL-encoded, as ``.../resource/<id>/<hash>/material-<id>.ggb``.
The script reads that URL and downloads the ZIP.  Private materials are
not visible to a signed-out request; the profile page has to list them
(public) or the file has to be exported from a signed-in browser.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _material_ids_from_profile(url: str) -> list[str]:
    """The public material ids linked from a profile page."""
    html = urllib.parse.unquote(_get(url))
    ids = re.findall(r"/m/([A-Za-z0-9]{8})(?=[\"'<])", html)
    return list(dict.fromkeys(ids))


def _download_url(material_id: str) -> str | None:
    """The `.ggb` URL embedded in a public material page."""
    try:
        page = urllib.parse.unquote(_get(f"https://www.geogebra.org/m/{material_id}"))
    except OSError:
        return None
    match = re.search(
        rf"https://www\.geogebra\.org/resource/{re.escape(material_id)}/"
        rf"[^\"'\\ ]+/material-{re.escape(material_id)}\.ggb",
        page,
    )
    return match.group(0) if match else None


def _download(material_id: str, out: Path) -> Path | None:
    url = _download_url(material_id)
    if url is None:
        print(f"{material_id}: no public .ggb URL", file=sys.stderr)
        return None
    target = out / f"{material_id}.ggb"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except OSError as exc:
        print(f"{material_id}: download failed: {exc}", file=sys.stderr)
        return None
    target.write_bytes(data)
    print(f"{material_id}: {len(data)} bytes -> {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="public GeoGebra profile URL")
    parser.add_argument("--ids", nargs="*", default=[], help="material ids")
    parser.add_argument("--out", default="geogebra_corpus", help="output folder")
    args = parser.parse_args()

    ids = list(args.ids)
    if args.profile:
        found = _material_ids_from_profile(args.profile)
        if not found:
            print(
                "profile has no public materials (private files are not "
                "visible without signing in)",
                file=sys.stderr,
            )
        ids.extend(found)
    ids = list(dict.fromkeys(ids))
    if not ids:
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    downloads = [path for material_id in ids if (path := _download(material_id, out))]
    print(f"downloaded {len(downloads)} / {len(ids)}")
    return 0 if downloads else 1


if __name__ == "__main__":
    raise SystemExit(main())
