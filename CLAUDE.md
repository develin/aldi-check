# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small tool that downloads the latest ALDI SÜD (Germany) weekly flyer ("Prospekt") and assembles it into a single PDF.

## Commands

```bash
pip install -r requirements.txt          # only dependency is Pillow
python download_prospekt.py              # downloads the latest flyer to aldi-sued-prospekt.pdf
python download_prospekt.py -o out.pdf   # custom output path
python download_prospekt.py --slug kw35-26-op  # fetch a specific flyer instead of auto-detecting the latest

python -m unittest test_download_prospekt.py -v   # run the test suite
python -m unittest test_download_prospekt.TestClassName.test_method_name  # run a single test
```

There is no build step or linter configured in this repo.

## Architecture

`download_prospekt.py` is a single-file script with no framework — everything goes through the stdlib `urllib.request` plus `PIL.Image` for PDF assembly. The interesting part is *how* it locates the current flyer, since ALDI SÜD's main site actively blocks scripted access:

- `www.aldi-sued.de` sits behind Akamai bot protection and returns HTTP 403 to non-browser clients (verified: plain `curl`/`urllib` requests are blocked even with a realistic User-Agent).
- The weekly flyers are actually served from a separate, unprotected Publitas-based viewer at `prospekt.aldi-sued.de`. Requesting the bare root of that host (`https://prospekt.aldi-sued.de/`) returns an HTTP redirect to the current week's flyer slug (e.g. `/kw34-26-op-mp/`). This is the mechanism the script relies on to find "the latest" flyer — it never touches the protected main site.
- Once the slug is known, `{BASE_HOST}/{slug}/spreads.json?page=N` returns a JSON manifest of "spreads" (a spread is 1 page for covers, 2 pages for interior spreads). Each page entry has an `images` dict keyed by resolution name (`at2400` down to `at200`). The manifest itself is paginated — a flyer with more spreads than fit on one page requires incrementing `page=N` until the server returns HTTP 400 or an empty list.
- Not every page is guaranteed to expose every resolution, so image URL selection walks a resolution preference list (`IMAGE_RESOLUTIONS`, highest first) rather than assuming a single key exists.

Pipeline in `download_flyer()`: resolve slug → paginate through `spreads.json` to collect one image URL per page → download each page image and decode with Pillow → save all page images as a single multi-page PDF (`Image.save(..., save_all=True, append_images=...)`).

Because this whole approach reverse-engineers an undocumented third-party site, treat the URL structure (`spreads.json`, the `images` resolution keys, the root-redirect trick) as fragile — if ALDI SÜD changes their flyer viewer, `resolve_latest_slug`, `collect_page_image_urls`, or `best_image_url` are the places that will need updating.

## Testing approach

`test_download_prospekt.py` mocks `urllib.request.urlopen`, the module's own `fetch()`, and `PIL.Image.open` — no test makes a real network call or decodes a real image. When adding tests for new HTTP-dependent behavior, follow this pattern rather than hitting the live site.
