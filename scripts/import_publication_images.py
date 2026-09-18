#!/usr/bin/env python3
"""Import only human-approved publication images listed in sources.json.

The script never discovers images or crawls publisher pages.  --dry-run is
network-free; --apply downloads only enabled, explicitly listed HTTPS image URLs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "assets" / "publications"
ASSET_PREFIX = PurePosixPath("assets/publications")
ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
REUSABLE_LICENSES = {"cc0", "public domain", "cc by", "cc-by", "cc by 4.0", "cc-by-4.0"}


def normalize_doi(value: str) -> str:
    """Return a lower-case DOI, accepting a DOI URL as input."""
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"/(?:meta|abstract|full|html|short|en)$", "", value, flags=re.IGNORECASE)
    match = DOI_PATTERN.search(value)
    if not match:
        raise ValueError(f"Invalid DOI: {value!r}")
    return match.group(0).lower()


def doi_from_publication(publication: dict[str, Any]) -> str | None:
    for candidate in (publication.get("doi"), publication.get("url")):
        if isinstance(candidate, str):
            try:
                return normalize_doi(candidate)
            except ValueError:
                pass
    return None


def is_https_url(value: Any) -> bool:
    return (isinstance(value, str) and not any(char.isspace() for char in value)
            and urlparse(value).scheme.lower() == "https" and bool(urlparse(value).netloc))


def is_reusable_license(value: Any) -> bool:
    return re.sub(r"\s+", " ", str(value).strip().lower()) in REUSABLE_LICENSES


def is_safe_local_asset_path(value: Any) -> bool:
    """Allow only image files below the publication asset directory."""
    if not isinstance(value, str) or "\\" in value:
        return False
    path = PurePosixPath(value)
    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.parts[:2] == ASSET_PREFIX.parts
        and len(path.parts) >= 3
        and path.suffix.lower() in allowed_extensions
    )


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def local_image_path(doi: str, kind: str, extension: str) -> str:
    path = ASSET_PREFIX / f"{safe_slug(doi)}-{safe_slug(kind)}.{extension}"
    result = path.as_posix()
    if not is_safe_local_asset_path(result):
        raise ValueError(f"Generated unsafe asset path: {result}")
    return result


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_source(source: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(source, dict):
        raise ValueError("Each source entry must be an object")
    doi = normalize_doi(str(source.get("doi", "")))
    image_url = source.get("image_url")
    if not is_https_url(image_url):
        raise ValueError(f"{doi}: image_url must be an explicit HTTPS URL")
    for field in ("kind", "source_name", "source_page", "license"):
        if not isinstance(source.get(field), str) or not source[field].strip():
            raise ValueError(f"{doi}: missing required field {field!r}")
    if not is_https_url(source["source_page"]):
        raise ValueError(f"{doi}: source_page must use HTTPS")
    if not is_reusable_license(source["license"]):
        raise ValueError(f"{doi}: licence is not auto-importable: {source['license']}")
    return doi, image_url


def download_image(url: str) -> tuple[bytes, str]:
    """Download one explicitly approved image and validate its response."""
    request = Request(url, headers={"User-Agent": "PlasmonicsLabImageImporter/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            status = getattr(response, "status", response.getcode())
            content_type = response.headers.get_content_type().lower()
            if status != 200 or content_type not in ALLOWED_CONTENT_TYPES:
                raise ValueError(f"{url}: expected 200 image response, got {status} {content_type}")
            payload = response.read(MAX_IMAGE_BYTES + 1)
    except (HTTPError, URLError) as error:
        raise ValueError(f"{url}: download failed: {error}") from error
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError(f"{url}: image exceeds {MAX_IMAGE_BYTES} bytes")
    if not payload:
        raise ValueError(f"{url}: empty response")
    signatures = {
        "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": payload.startswith(b"\xff\xd8\xff"),
        "image/gif": payload[:6] in {b"GIF87a", b"GIF89a"},
        "image/webp": payload[:4] == b"RIFF" and payload[8:12] == b"WEBP",
    }
    if not signatures.get(content_type, False):
        raise ValueError(f"{url}: response bytes do not match {content_type}")
    return payload, ALLOWED_CONTENT_TYPES[content_type]


def verified_image_metadata(source: dict[str, Any], relative_path: str, digest: str) -> dict[str, Any]:
    return {
        "path": relative_path,
        "kind": source["kind"],
        "status": "verified",
        "source_url": source["image_url"],
        "source_page": source["source_page"],
        "source_name": source["source_name"],
        "license": source["license"],
        "license_url": source.get("license_url", ""),
        "rights_note": source.get("rights_note", ""),
        "checked_at": source.get("checked_at", date.today().isoformat()),
        "sha256": digest,
    }


def find_publication(publications: list[dict[str, Any]], doi: str) -> dict[str, Any] | None:
    return next((item for item in publications if doi_from_publication(item) == doi), None)


def import_sources(sources_path: Path, publications_path: Path, apply: bool, candidates: bool = False) -> int:
    source_data = load_json(sources_path)
    if candidates:
        sources = [item for item in source_data.get("candidates", []) if item.get("status") == "verified"]
    else:
        sources = source_data.get("sources", []) if isinstance(source_data, dict) else source_data
    publications = load_json(publications_path)
    if not isinstance(sources, list) or not isinstance(publications, list):
        raise ValueError("sources and publications must both be JSON arrays (sources may be inside {\"sources\": [...]})")

    enabled_sources = [item for item in sources if item.get("enabled", True)]
    if not enabled_sources:
        print("No enabled sources. Nothing to import.")
        return 0

    changes = 0
    for source in enabled_sources:
        doi, image_url = validate_source(source)
        publication = find_publication(publications, doi)
        if publication is None:
            raise ValueError(f"{doi}: no matching publication in {publications_path.name}")
        if not apply:
            print(f"DRY RUN: would download {image_url} and update {doi}")
            changes += 1
            continue

        payload, extension = download_image(image_url)
        relative_path = local_image_path(doi, source["kind"], extension)
        target = PROJECT_ROOT / Path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=target.parent) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        temporary_path.replace(target)

        publication["doi"] = doi
        publication["image"] = verified_image_metadata(
            source, relative_path, hashlib.sha256(payload).hexdigest()
        )
        print(f"IMPORTED: {doi} -> {relative_path}")
        changes += 1

    if apply and changes:
        publications_path.write_text(
            json.dumps(publications, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Updated {publications_path}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ASSET_DIR / "sources.json")
    parser.add_argument("--candidates", type=Path, help="Import only verified direct-image records from this report.")
    parser.add_argument("--publications", type=Path, default=PROJECT_ROOT / "publications.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate only; make no network or file changes (default).")
    mode.add_argument("--apply", action="store_true", help="Download enabled approved sources and update publications.json.")
    args = parser.parse_args()
    input_path = args.candidates or args.sources
    return 0 if import_sources(input_path, args.publications, apply=args.apply, candidates=bool(args.candidates)) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
