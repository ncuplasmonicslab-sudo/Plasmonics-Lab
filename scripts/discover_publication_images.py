#!/usr/bin/env python3
"""Conservatively discover public image candidates from public metadata APIs.

Queries only Crossref, OpenAlex and Europe PMC; never publisher pages or search
engines. Cache results. A 403, 429, CAPTCHA/login/paywall response blocks the
domain for the rest of the run. This tool does not download images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from import_publication_images import normalize_doi

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "publications"
ENDPOINTS = {
    "Crossref": "https://api.crossref.org/works/",
    "OpenAlex": "https://api.openalex.org/works/https://doi.org/",
    "Europe PMC": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&query=DOI:%22",
    "Zenodo": "https://zenodo.org/api/records?q=doi:%22",
}
BLOCK_WORDS = ("captcha", "robot", "login", "sign in", "paywall", "forbidden", "rate limit")
USER_AGENT = "PlasmonicsLabPublicImageDiscovery/1.0 (+local academic site)"
DEFAULT_RETRY_DELAY = timedelta(hours=24)

def load(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def doi_of(publication: dict[str, Any]) -> str | None:
    for value in (publication.get("doi"), publication.get("url")):
        if isinstance(value, str):
            try: return normalize_doi(value)
            except ValueError: pass
    return None

def record_id(publication: dict[str, Any], doi: str | None) -> str:
    if doi: return "doi:" + doi
    title = " ".join(str(publication.get("title", "")).lower().split())
    return "title:" + hashlib.sha256(title.encode()).hexdigest()[:16]

def source_statistics(cache: dict[str, Any]) -> dict[str, Any]:
    """Rebuild cumulative network statistics from cached unique URLs."""
    stats: dict[str, dict[str, Any]] = {}
    for group, field in (("responses", "successes"), ("errors", "non_successes")):
        for key in cache.get(group, {}):
            host = key.split("/")[2]
            stats.setdefault(host, {"queries": 0, "successes": 0, "non_successes": 0})
            stats[host][field] += 1
    for host, reason in cache.get("blocked_reasons", {}).items():
        stats.setdefault(host, {"queries": 0, "successes": 0, "non_successes": 0})
        # Block responses are deliberately not cached as ordinary errors.
        stats[host]["queries"] += 1
        stats[host]["stopped_reason"] = reason.get("reason", "access restriction")
    for values in stats.values(): values["queries"] += values["successes"] + values["non_successes"]
    return stats

class Client:
    def __init__(self, cache: dict[str, Any], delay: float, dry_run: bool = False):
        self.cache, self.delay, self.dry_run = cache, delay, dry_run
        # A 403/429 stops only that source, and only until its retry time.
        # Legacy blocks have no observed time; migrate them conservatively once
        # instead of clearing or immediately retrying them.
        self.blocked = set()
        reasons = cache.setdefault("blocked_reasons", {})
        now = datetime.now(timezone.utc)
        for host in cache.get("blocked_domains", []):
            reason = reasons.setdefault(host, {"reason": "prior run access restriction"})
            if not reason.get("retry_after"):
                reason["retry_after"] = (now + DEFAULT_RETRY_DELAY).isoformat()
                reason["reason"] = reason.get("reason", "prior run access restriction") + "; retry time was unavailable"
            self.blocked.add(host)
        cache["blocked_domains"] = sorted(self.blocked)
        self.stats = cache.setdefault("source_stats", {})
    def stat(self, host: str, key: str, value: int = 1) -> None:
        self.stats.setdefault(host, {}).setdefault(key, 0)
        self.stats[host][key] += value
    def get(self, url: str) -> tuple[str, Any]:
        host, key = url.split("/")[2], "json:" + url
        if host in self.blocked:
            reason = self.cache["blocked_reasons"].get(host, {})
            retry_after = reason.get("retry_after")
            try:
                retry_time = datetime.fromisoformat(retry_after.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                retry_time = datetime.now(timezone.utc) + DEFAULT_RETRY_DELAY
                reason["retry_after"] = retry_time.isoformat()
            if datetime.now(timezone.utc) < retry_time:
                return "deferred", {"reason": reason.get("reason", "access restriction"), "retry_after": reason["retry_after"]}
            self.blocked.remove(host)
            self.cache["blocked_domains"] = sorted(self.blocked)
            self.cache["blocked_reasons"].pop(host, None)
        if key in self.cache.get("responses", {}): return "cached", self.cache["responses"][key]
        if key in self.cache.get("errors", {}): return "cached_error", self.cache["errors"][key]
        if self.dry_run: return "not_checked", {"reason": "dry run; no network request"}
        self.stat(host, "queries")
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}), timeout=8) as response:
                status, content_type = response.getcode(), response.headers.get_content_type()
                body = response.read().decode("utf-8", "replace")
        except HTTPError as error:
            status, content_type = error.code, error.headers.get_content_type() if error.headers else ""
            body = error.read().decode("utf-8", "replace")
        except (URLError, TimeoutError, OSError) as error:
            error_data = {"reason": str(error)}
            self.cache.setdefault("errors", {})[key] = error_data
            return "error", error_data
        is_html_restriction = content_type == "text/html" and any(word in body.lower() for word in BLOCK_WORDS)
        if status in (403, 429) or is_html_restriction:
            self.blocked.add(host); self.cache["blocked_domains"] = sorted(self.blocked)
            retry_after = (datetime.now(timezone.utc) + DEFAULT_RETRY_DELAY).isoformat()
            self.cache.setdefault("blocked_reasons", {})[host] = {
                "status": status, "reason": "access restriction", "retry_after": retry_after,
            }
            self.stats.setdefault(host, {})["stopped_reason"] = f"HTTP {status} access restriction"
            return "deferred", {"status": status, "reason": "access restriction", "retry_after": retry_after}
        if status != 200 or content_type != "application/json":
            error_data = {"status": status, "content_type": content_type}
            self.cache.setdefault("errors", {})[key] = error_data
            return "error", error_data
        try: data = json.loads(body)
        except json.JSONDecodeError:
            error_data = {"reason": "invalid JSON"}; self.cache.setdefault("errors", {})[key] = error_data
            return "error", error_data
        self.cache.setdefault("responses", {})[key] = data
        self.stat(host, "successes")
        time.sleep(self.delay)
        return "ok", data

def inspect(publication: dict[str, Any], client: Client) -> dict[str, Any]:
    doi = doi_of(publication)
    result = {"publication_id": record_id(publication, doi), "title": publication.get("title", ""), "doi": doi,
              "status": "no_candidate", "candidates": [], "attempts": [], "checked_at": date.today().isoformat()}
    if not doi:
        title = str(publication.get("title", "")).strip()
        if not title:
            result["notes"] = ["No DOI or usable title."]; return result
        state, data = client.get("https://api.openalex.org/works?per-page=1&search=" + quote(title))
        result["attempts"].append({"source": "OpenAlex title fallback", "outcome": state})
        cross_state, cross_data = client.get("https://api.crossref.org/works?rows=1&query.title=" + quote(title))
        result["attempts"].append({"source": "Crossref title fallback", "outcome": cross_state})
        matches = data.get("results", []) if state in {"ok", "cached"} else []
        if matches and " ".join(matches[0].get("title", "").lower().split()) == " ".join(title.lower().split()):
            result["notes"] = ["Exact title metadata match found, but no direct reusable image URL was inferred."]
        else:
            result["notes"] = ["No exact title metadata match; no image candidate inferred."]
        if any(item["outcome"] == "deferred" for item in result["attempts"]):
            result["status"] = "deferred"
        return result
    urls = {
        "Crossref": ENDPOINTS["Crossref"] + quote(doi, safe=""),
        "OpenAlex": ENDPOINTS["OpenAlex"] + quote(doi, safe=""),
        "Europe PMC": ENDPOINTS["Europe PMC"] + quote(doi, safe="") + "%22",
        "Zenodo": ENDPOINTS["Zenodo"] + quote(doi, safe="") + "%22&size=1",
    }
    states: dict[str, tuple[str, Any]] = {}
    for source, url in urls.items():
        states[source] = client.get(url)
        result["attempts"].append({"source": source, "outcome": states[source][0]})
    epmc = states["Europe PMC"][1] if states["Europe PMC"][0] in {"ok", "cached"} else {}
    for entry in epmc.get("resultList", {}).get("result", []):
        pmcid, license_name = entry.get("pmcid"), entry.get("license") or entry.get("licence")
        if pmcid:
            result["candidates"].append({"kind": "article_repository_record", "source_name": "Europe PMC", "pmcid": pmcid,
                "source_page": f"https://europepmc.org/article/MED/{entry.get('id', '')}", "license": license_name or "unknown",
                "rights_note": "Repository record found; no direct figure URL was inferred automatically."})
            result["status"] = "needs_review"
    if result["status"] == "no_candidate" and any(state == "deferred" for state, _ in states.values()):
        result["status"] = "deferred"
    return result

def manual_review_entry(publication: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Make a conservative review record without inventing an image candidate."""
    doi = result.get("doi")
    title = str(publication.get("title", ""))
    source_page = (
        ENDPOINTS["Crossref"] + quote(doi, safe="")
        if doi else "https://api.crossref.org/works?rows=1&query.title=" + quote(title)
    )
    repository = next((item for item in result.get("candidates", []) if item.get("source_page")), None)
    legacy = publication.get("img_scr")
    legacy_url = legacy[0] if isinstance(legacy, list) and legacy and isinstance(legacy[0], str) and legacy[0].startswith("https://") else None
    if repository:
        candidate_page, source_name = repository["source_page"], repository.get("source_name", "public repository")
        license_status = repository.get("license", "unknown")
        reason = "Repository record is public, but a direct image and reusable licence were not verified."
    elif legacy_url:
        candidate_page, source_name = legacy_url, "existing HTTPS publisher image"
        license_status = "unknown"
        reason = "Existing HTTPS image remains for display, but its reusable licence is not verified for local import."
    else:
        candidate_page, source_name = None, "Crossref public metadata"
        license_status = "not established"
        reason = "No direct public image with a confirmed reusable licence was found; do not infer a publisher image."
    if result["status"] == "deferred":
        reason += " One or more permitted metadata sources are deferred until their retry time."
    return {
        "publication_id": result["publication_id"], "title": title, "doi": doi,
        "status": "manual_needed", "source_page": source_page,
        "candidate_image_page": candidate_page, "source_name": source_name,
        "license_status": license_status,
        "suggested_image_type": "figure 1 (manual selection and rights confirmation required)",
        "reason_not_auto_imported": reason,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publications", type=Path, default=ROOT / "publications.json")
    parser.add_argument("--cache", type=Path, default=ASSETS / "discovery-cache.json")
    parser.add_argument("--report", type=Path, default=ASSETS / "candidates.json")
    parser.add_argument("--manual-review", type=Path, default=ASSETS / "manual-image-review.json")
    parser.add_argument("--start", type=int, default=0, help="Zero-based publication offset; enables resumable batches.")
    parser.add_argument("--limit", type=int); parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Use cached metadata only; do not make network requests.")
    parser.add_argument("--delay", type=float, default=0.4)
    args = parser.parse_args(); publications = load(args.publications, [])
    cache = {} if args.refresh else load(args.cache, {"responses": {}, "blocked_domains": []})
    client, results = Client(cache, args.delay, args.dry_run), []
    stop = args.start + args.limit if args.limit else None
    for publication in publications[args.start:stop]:
        results.append(inspect(publication, client)); save(args.cache, cache)
    summary = {key: sum(item["status"] == key for item in results) for key in ("verified", "needs_review", "deferred", "no_candidate")}
    save(args.report, {"generated_at": date.today().isoformat(), "policy": "Only CC0, Public Domain, or CC BY direct images may be verified.",
                       "summary": summary, "candidates": results, "blocked_domains": sorted(client.blocked), "source_stats": source_statistics(cache)})
    save(args.manual_review, {"generated_at": date.today().isoformat(),
                              "policy": "Review only publicly accessible sources; do not import until direct image ownership and CC0, Public Domain, or CC BY reuse are confirmed.",
                              "manual_review": [manual_review_entry(publication, result) for publication, result in zip(publications[args.start:stop], results)]})
    print(json.dumps(summary)); return 0

if __name__ == "__main__": raise SystemExit(main())
