#!/usr/bin/env python3
"""Download the latest ALDI SÜD (Germany) prospekt (flyer) as a PDF.

ALDI SÜD publishes its weekly flyers through a Publitas-based viewer at
https://prospekt.aldi-sued.de/. The root of that host redirects to the
slug of the current week's flyer (e.g. /kw34-26-op-mp/), which lets us
find the latest prospekt without touching the bot-protected main
www.aldi-sued.de site. Each flyer exposes a spreads.json manifest with
per-page image URLs at several resolutions; this script downloads the
highest resolution available and assembles the pages into a single PDF.
"""

import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

from PIL import Image

BASE_HOST = "https://prospekt.aldi-sued.de"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
IMAGE_RESOLUTION = "at2400"  # highest resolution offered by the viewer


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def resolve_latest_slug() -> str:
    """Follow the redirect on the prospekt root to find the current flyer slug."""
    request = urllib.request.Request(f"{BASE_HOST}/", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = response.geturl()
    match = re.search(r"/([\w-]+)/?$", final_url.rstrip("/"))
    if not match:
        raise RuntimeError(f"Could not determine flyer slug from redirect target: {final_url}")
    return match.group(1)


def collect_page_image_urls(slug: str) -> list:
    manifest = json.loads(fetch(f"{BASE_HOST}/{slug}/spreads.json?page=1"))
    urls = []
    for spread in manifest:
        for page in spread["pages"]:
            urls.append(BASE_HOST + page["images"][IMAGE_RESOLUTION])
    return urls


def download_flyer(output_path: Path, slug: str = None) -> Path:
    slug = slug or resolve_latest_slug()
    print(f"Fetching prospekt '{slug}'...")

    urls = collect_page_image_urls(slug)
    if not urls:
        raise RuntimeError("No pages found for this flyer.")

    print(f"Downloading {len(urls)} pages...")
    images = []
    for index, url in enumerate(urls, start=1):
        print(f"  page {index}/{len(urls)}")
        images.append(Image.open(io.BytesIO(fetch(url))).convert("RGB"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(output_path, save_all=True, append_images=images[1:])
    print(f"Saved {len(images)} pages to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output", default="aldi-sued-prospekt.pdf", help="Output PDF path"
    )
    parser.add_argument(
        "--slug",
        help="Specific flyer slug (e.g. kw34-26-op-mp) instead of auto-detecting the latest",
    )
    args = parser.parse_args()

    try:
        download_flyer(Path(args.output), slug=args.slug)
    except (HTTPError, URLError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
