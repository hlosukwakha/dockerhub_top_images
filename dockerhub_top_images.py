#!/usr/bin/env python3
# Crawl Docker Hub search results using Playwright (headless Chromium)
# pip install playwright bs4
# python -m playwright install chromium

import asyncio, json, re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SEARCH_URL_TMPL = "https://hub.docker.com/search?q=&type=image&order=desc&sort={sort}&page={page}"

@dataclass
class RepoRow:
    name: str          # repository name only (e.g., "nginx")
    owner: str         # namespace/owner (e.g., "library")
    pulls: str         # e.g., "10M+", "1B+", or "12,345,678"
    stars: int
    last_updated: str
    url: str

SEARCH_JSON_PATTERNS = (
    "/api/search",
    "/api/content/v1/products/search",
    "/v2/search/repositories",
    "/search/repositories",
)

def split_owner_repo(ns: str, name: str) -> (str, str):
    """Return (owner, repo) ensuring no double-slashed names."""
    ns = (ns or "").strip("/")
    name = (name or "").strip("/")
    # If name already contains a slash, split once
    if "/" in name:
        parts = name.split("/", 1)
        return parts[0], parts[1]
    return ns, name

def parse_search_json(payload: Dict[str, Any]) -> List[RepoRow]:
    rows: List[RepoRow] = []
    candidates = None
    for key in ("summaries", "results", "data", "items"):
        if isinstance(payload.get(key), list):
            candidates = payload[key]
            break
    if not candidates:
        for v in payload.values():
            if isinstance(v, dict):
                for kk in ("summaries", "results", "items"):
                    if isinstance(v.get(kk), list):
                        candidates = v[kk]; break
            if candidates: break
    if not candidates: return rows

    for it in candidates:
        # Extract owner + name explicitly
        ns = it.get("namespace") or it.get("publisher") or it.get("orgname") or ""
        base_name = it.get("name") or it.get("slug") or it.get("repo_name") or it.get("display_name") or ""
        owner, repo = split_owner_repo(ns, base_name)

        # Pulls
        pulls_val = it.get("pulls") or it.get("pull_count_str") or it.get("pull_count") or ""
        if isinstance(pulls_val, int):
            pulls = f"{pulls_val:,}"
        else:
            pulls = str(pulls_val)

        # Stars
        star_val = it.get("star_count") or it.get("stars") or 0
        try:
            stars = int(str(star_val).replace(",", ""))
        except:
            stars = 0

        updated = it.get("last_updated") or it.get("updated_at") or ""
        link = it.get("href") or f"/r/{owner}/{repo}" if owner and repo else ""
        if link.startswith("/"):
            link = "https://hub.docker.com" + link

        if owner and repo:
            rows.append(RepoRow(
                name=repo, owner=owner, pulls=pulls, stars=stars,
                last_updated=str(updated), url=link
            ))
    return rows

def parse_from_dom(html: str) -> List[RepoRow]:
    """Fallback DOM scrape that fills Name, Owner, Pulls, Stars, Last Updated, URL."""
    soup = BeautifulSoup(html, "html.parser")
    rows: List[RepoRow] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Expect /r/<owner>/<repo>
        m = re.match(r"^/r/([^/]+)/([^/]+)/?$", href)
        if not m: 
            continue
        owner, repo = m.group(1), m.group(2)
        text = a.get_text(" ", strip=True) or ""
        pulls = _m(r"Pulls\.\s*([0-9A-Za-z+.,]+)", text) or _m(r"([0-9A-Za-z+.,]+)\s+Pulls", text) or ""
        stars_str = _m(r"Stars\.\s*([0-9,]+)", text) or _m(r"([0-9,]+)\s+Stars", text) or "0"
        try:
            stars = int(stars_str.replace(",", ""))
        except:
            stars = 0
        updated = _m(r"Last Updated\.\s*([^\n]+)", text) or _m(r"Updated\s*([^\n]+)", text) or ""
        url = "https://hub.docker.com" + href
        rows.append(RepoRow(name=repo, owner=owner, pulls=pulls, stars=stars, last_updated=updated, url=url))
    return rows

def _m(rx, s):
    m = re.search(rx, s, re.I)
    return m.group(1) if m else None

async def fetch_sorted(sort: str, n: int) -> List[RepoRow]:
    """Navigate like a user, capture the search JSON, parse it; fallback to DOM if needed."""
    out: List[RepoRow] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        async def maybe_parse(resp):
            if not any(pat in resp.url for pat in SEARCH_JSON_PATTERNS): 
                return []
            try:
                if "json" not in (resp.headers.get("content-type") or ""):
                    return []
                return parse_search_json(await resp.json())
            except:
                return []

        page_no = 1
        seen = set()
        while len(out) < n and page_no <= 50:
            url = SEARCH_URL_TMPL.format(sort=sort, page=page_no)
            batch: List[RepoRow] = []

            async def on_response(resp):
                rows = await maybe_parse(resp)
                if rows: batch.extend(rows)

            page.on("response", on_response)
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(0.5)  # buffer for late XHRs
            page.remove_listener("response", on_response)

            if not batch:
                html = await page.content()
                batch = parse_from_dom(html)

            # de-dup and collect
            for r in batch:
                key = (r.owner, r.name)
                if key in seen: 
                    continue
                seen.add(key); out.append(r)
                if len(out) >= n:
                    break

            if not batch:
                break
            page_no += 1

        await browser.close()
    return out[:n]

async def main(top=25, latest=10, out="table"):
    top_pulls = await fetch_sorted("pulls", top)
    top_stars = await fetch_sorted("stars", top)
    latest10  = await fetch_sorted("updated_at", latest)

    if out == "json":
        print(json.dumps({
            "top_by_pulls": [asdict(x) for x in top_pulls],
            "top_by_stars": [asdict(x) for x in top_stars],
            "latest": [asdict(x) for x in latest10],
        }, indent=2))
        return

    def pt(title, data):
        print("\n" + title + "\n" + "="*len(title))
        # Exact header mapping requested
        print(f"{'Name':<32} {'Owner':<24} {'Pulls':<10} {'Stars':>7}  {'Last Updated':<22} URL")
        print("-" * 120)
        for r in data:
            print(f"{r.name:<32} {r.owner:<24} {r.pulls:<10} {r.stars:>7}  {r.last_updated:<22} {r.url}")

    pt(f"Top {top} images by pulls", top_pulls)
    pt(f"Top {top} images by stars", top_stars)
    pt(f"Latest {latest} images (by last updated)", latest10)

if __name__ == "__main__":
    import argparse, asyncio
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--latest", type=int, default=10)
    ap.add_argument("--out", choices=["table","json"], default="table")
    args = ap.parse_args()
    asyncio.run(main(args.top, args.latest, args.out))
