"""Offline checks for the publication-image importer and renderer contract."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import import_publication_images as importer  # noqa: E402
import discover_publication_images as discovery  # noqa: E402


class PublicationImageSafetyTests(unittest.TestCase):
    def test_https_is_required(self) -> None:
        self.assertTrue(importer.is_https_url("https://example.org/image.png"))
        self.assertFalse(importer.is_https_url("http://example.org/image.png"))
        self.assertFalse(importer.is_https_url("assets/publications/image.png"))

    def test_only_reusable_licences_can_be_auto_imported(self) -> None:
        self.assertTrue(importer.is_reusable_license("CC BY 4.0"))
        self.assertTrue(importer.is_reusable_license("CC0"))
        self.assertFalse(importer.is_reusable_license("CC BY-NC 4.0"))
        self.assertFalse(importer.is_reusable_license("unknown"))

    def test_traversal_path_is_rejected(self) -> None:
        self.assertTrue(importer.is_safe_local_asset_path("assets/publications/example.png"))
        self.assertFalse(importer.is_safe_local_asset_path("assets/publications/../secret.png"))
        self.assertFalse(importer.is_safe_local_asset_path("../assets/publications/example.png"))
        self.assertFalse(importer.is_safe_local_asset_path("/assets/publications/example.png"))

    def test_doi_creates_stable_safe_filename(self) -> None:
        path = importer.local_image_path("10.1021/acsaelm.4c02220", "graphic_abstract", "png")
        self.assertEqual(path, "assets/publications/10-1021-acsaelm-4c02220-graphic-abstract.png")
        self.assertTrue(importer.is_safe_local_asset_path(path))

    def test_doi_url_suffix_is_not_part_of_doi(self) -> None:
        self.assertEqual(importer.normalize_doi("https://iopscience.iop.org/article/10.1088/2515-7647/ae965f/meta"), "10.1088/2515-7647/ae965f")

    def test_default_cover_and_renderer_never_use_empty_src(self) -> None:
        cover = PROJECT_ROOT / "assets" / "publications" / "default-cover.svg"
        renderer = (PROJECT_ROOT / "script.js").read_text(encoding="utf-8")
        self.assertTrue(cover.is_file())
        self.assertIn("const PUBLICATION_DEFAULT_COVER = 'assets/publications/default-cover.svg';", renderer)
        self.assertIn("return PUBLICATION_DEFAULT_COVER;", renderer)
        self.assertIn('src="${publicationImageSrc}"', renderer)
        self.assertNotIn('src="${pub.img_scr}"', renderer)
        self.assertNotIn('src=""', renderer)

    def test_missing_doi_uses_conservative_title_fallback(self) -> None:
        record = discovery.inspect({"title": "Potentially ambiguous title"}, discovery.Client({"responses": {}, "blocked_domains": []}, 0, dry_run=True))
        self.assertEqual(record["status"], "no_candidate")
        self.assertEqual(record["attempts"][0]["outcome"], "not_checked")
        self.assertEqual(record["attempts"][1]["outcome"], "not_checked")

    def test_openalex_block_does_not_block_other_sources_or_record(self) -> None:
        class IndependentSources:
            def get(self, url):
                if "openalex" in url:
                    return "blocked", {"reason": "HTTP 429"}
                if "europepmc" in url:
                    return "cached", {"resultList": {"result": []}}
                return "cached", {"message": {}}
        record = discovery.inspect({"title": "Example", "url": "https://doi.org/10.1234/example.001"}, IndependentSources())
        self.assertEqual(record["status"], "no_candidate")
        self.assertEqual(len(record["attempts"]), 4)
        self.assertIn("cached", [attempt["outcome"] for attempt in record["attempts"]])

    def test_legacy_rate_limit_is_deferred_not_no_candidate(self) -> None:
        cache = {
            "responses": {},
            "blocked_domains": ["api.openalex.org"],
            "blocked_reasons": {"api.openalex.org": {"status": 429, "reason": "access restriction"}},
        }
        client = discovery.Client(cache, 0, dry_run=True)
        state, detail = client.get("https://api.openalex.org/works?search=example")
        self.assertEqual(state, "deferred")
        self.assertIn("retry_after", detail)

    def test_deferred_source_prevents_no_candidate_status(self) -> None:
        class DeferredSources:
            def get(self, url):
                if "openalex" in url:
                    return "deferred", {"retry_after": "2099-01-01T00:00:00+00:00"}
                return "cached", {"message": {}}
        record = discovery.inspect({"title": "Example", "url": "https://doi.org/10.1234/example.001"}, DeferredSources())
        self.assertEqual(record["status"], "deferred")

    def test_source_statistics_are_independent(self) -> None:
        stats = discovery.source_statistics({
            "responses": {"json:https://crossref.example/a": {}, "json:https://crossref.example/b": {}},
            "errors": {"json:https://zenodo.example/a": {}},
            "blocked_reasons": {"zenodo.example": {"reason": "access restriction"}},
        })
        self.assertEqual(stats["crossref.example"]["queries"], 2)
        self.assertEqual(stats["zenodo.example"]["queries"], 2)
        self.assertEqual(stats["zenodo.example"]["stopped_reason"], "access restriction")


if __name__ == "__main__":
    unittest.main()
