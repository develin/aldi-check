"""Unit tests for download_prospekt.py.

All tests run fully offline: urllib, network fetches and PIL image decoding
are mocked out so no real HTTP requests or image processing ever happen.
"""

import json
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import download_prospekt as dp


class ResolveLatestSlugTests(unittest.TestCase):
    def _mock_urlopen(self, final_url):
        cm = mock.MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.geturl.return_value = final_url
        return cm

    def test_extracts_slug_from_redirected_url(self):
        cm = self._mock_urlopen("https://prospekt.aldi-sued.de/kw34-26-op-mp/")
        with mock.patch.object(dp.urllib.request, "urlopen", return_value=cm) as mock_urlopen:
            slug = dp.resolve_latest_slug()

        self.assertEqual(slug, "kw34-26-op-mp")
        mock_urlopen.assert_called_once()

    def test_extracts_slug_without_trailing_slash(self):
        cm = self._mock_urlopen("https://prospekt.aldi-sued.de/kw34-26-op-mp")
        with mock.patch.object(dp.urllib.request, "urlopen", return_value=cm):
            slug = dp.resolve_latest_slug()

        self.assertEqual(slug, "kw34-26-op-mp")

    def test_extracts_slug_ignoring_query_string(self):
        cm = self._mock_urlopen("https://prospekt.aldi-sued.de/kw34-26-op-mp/?utm_source=x")
        with mock.patch.object(dp.urllib.request, "urlopen", return_value=cm):
            slug = dp.resolve_latest_slug()

        self.assertEqual(slug, "kw34-26-op-mp")

    def test_raises_runtime_error_when_slug_cannot_be_determined(self):
        # The URL path is just "/", which has no non-empty last segment.
        cm = self._mock_urlopen("https://prospekt.aldi-sued.de/")
        with mock.patch.object(dp.urllib.request, "urlopen", return_value=cm):
            with self.assertRaises(RuntimeError):
                dp.resolve_latest_slug()


class BestImageUrlTests(unittest.TestCase):
    def test_prefers_highest_configured_resolution(self):
        page = {"images": {"at2400": "/a-2400.jpg", "at2000": "/a-2000.jpg"}}
        self.assertEqual(dp.best_image_url(page), f"{dp.BASE_HOST}/a-2400.jpg")

    def test_falls_back_when_preferred_resolution_missing(self):
        page = {"images": {"at1200": "/a-1200.jpg", "at600": "/a-600.jpg"}}
        self.assertEqual(dp.best_image_url(page), f"{dp.BASE_HOST}/a-1200.jpg")

    def test_raises_when_no_known_resolution_present(self):
        page = {"images": {"unknown": "/a.jpg"}}
        with self.assertRaises(RuntimeError):
            dp.best_image_url(page)


class CollectPageImageUrlsTests(unittest.TestCase):
    def test_flattens_and_filters_to_configured_resolution(self):
        manifest = [
            {
                "pages": [
                    {
                        "images": {
                            "at2400": "/slug/page1-2400.jpg",
                            "at2000": "/slug/page1-2000.jpg",
                        }
                    }
                ]
            },
            {
                "pages": [
                    {
                        "images": {
                            "at2400": "/slug/page2-2400.jpg",
                            "at2000": "/slug/page2-2000.jpg",
                        }
                    },
                    {
                        "images": {
                            "at2400": "/slug/page3-2400.jpg",
                            "at2000": "/slug/page3-2000.jpg",
                        }
                    },
                ]
            },
        ]
        not_found = HTTPError(url="x", code=400, msg="Invalid page", hdrs=None, fp=None)

        with mock.patch.object(
            dp, "fetch", side_effect=[json.dumps(manifest), not_found]
        ) as mock_fetch:
            urls = dp.collect_page_image_urls("kw34-26-op-mp")

        mock_fetch.assert_has_calls(
            [
                mock.call(f"{dp.BASE_HOST}/kw34-26-op-mp/spreads.json?page=1"),
                mock.call(f"{dp.BASE_HOST}/kw34-26-op-mp/spreads.json?page=2"),
            ]
        )
        self.assertEqual(
            urls,
            [
                f"{dp.BASE_HOST}/slug/page1-2400.jpg",
                f"{dp.BASE_HOST}/slug/page2-2400.jpg",
                f"{dp.BASE_HOST}/slug/page3-2400.jpg",
            ],
        )

    def test_stops_on_empty_manifest_page(self):
        with mock.patch.object(
            dp, "fetch", side_effect=[json.dumps([]), json.dumps([{"pages": []}])]
        ) as mock_fetch:
            urls = dp.collect_page_image_urls("kw34-26-op-mp")

        mock_fetch.assert_called_once_with(f"{dp.BASE_HOST}/kw34-26-op-mp/spreads.json?page=1")
        self.assertEqual(urls, [])

    def test_reraises_http_error_on_first_page(self):
        first_page_error = HTTPError(url="x", code=500, msg="Server error", hdrs=None, fp=None)
        with mock.patch.object(dp, "fetch", side_effect=first_page_error):
            with self.assertRaises(HTTPError):
                dp.collect_page_image_urls("kw34-26-op-mp")

    def test_reraises_non_400_http_error_on_later_page(self):
        manifest = [{"pages": [{"images": {"at2400": "/slug/page1-2400.jpg"}}]}]
        later_page_error = HTTPError(url="x", code=500, msg="Server error", hdrs=None, fp=None)
        with mock.patch.object(
            dp, "fetch", side_effect=[json.dumps(manifest), later_page_error]
        ):
            with self.assertRaises(HTTPError):
                dp.collect_page_image_urls("kw34-26-op-mp")


class DownloadFlyerTests(unittest.TestCase):
    def test_raises_runtime_error_when_no_pages_found(self):
        with mock.patch.object(dp, "resolve_latest_slug", return_value="slug") as mock_resolve, \
             mock.patch.object(dp, "collect_page_image_urls", return_value=[]) as mock_collect:
            with self.assertRaises(RuntimeError):
                dp.download_flyer(Path("out.pdf"))

        mock_resolve.assert_called_once()
        mock_collect.assert_called_once_with("slug")

    def test_downloads_and_saves_pdf(self):
        urls = [f"{dp.BASE_HOST}/a.jpg", f"{dp.BASE_HOST}/b.jpg", f"{dp.BASE_HOST}/c.jpg"]

        fake_images = [mock.MagicMock(name=f"image{i}") for i in range(len(urls))]
        for img in fake_images:
            img.convert.return_value = img

        with mock.patch.object(dp, "resolve_latest_slug", return_value="slug") as mock_resolve, \
             mock.patch.object(dp, "collect_page_image_urls", return_value=urls) as mock_collect, \
             mock.patch.object(dp, "fetch", return_value=b"fake-bytes") as mock_fetch, \
             mock.patch.object(dp.Image, "open", side_effect=fake_images) as mock_open:

            output_path = mock.MagicMock(spec=Path)
            result = dp.download_flyer(output_path)

        mock_resolve.assert_called_once()
        mock_collect.assert_called_once_with("slug")
        self.assertEqual(mock_fetch.call_count, len(urls))
        self.assertEqual(mock_open.call_count, len(urls))

        output_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        fake_images[0].save.assert_called_once_with(
            output_path, save_all=True, append_images=fake_images[1:]
        )
        self.assertIs(result, output_path)

    def test_explicit_slug_skips_resolve_latest_slug(self):
        urls = [f"{dp.BASE_HOST}/a.jpg"]
        fake_image = mock.MagicMock()
        fake_image.convert.return_value = fake_image

        with mock.patch.object(dp, "resolve_latest_slug") as mock_resolve, \
             mock.patch.object(dp, "collect_page_image_urls", return_value=urls) as mock_collect, \
             mock.patch.object(dp, "fetch", return_value=b"fake-bytes"), \
             mock.patch.object(dp.Image, "open", return_value=fake_image):

            output_path = mock.MagicMock(spec=Path)
            dp.download_flyer(output_path, slug="kw34-26-op-mp")

        mock_resolve.assert_not_called()
        mock_collect.assert_called_once_with("kw34-26-op-mp")


if __name__ == "__main__":
    unittest.main()
