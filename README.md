# Docker Hub Top Images Crawler (Playwright)

Fetch **Top Docker Hub images** by Pulls and Stars, plus the **latest** images, by crawling the Hub search UI with a real headless browser (Playwright).

Why Playwright? The former global Docker Hub API endpoint for "top across all Hub" is no longer publicly available and the search page is **client‑rendered** (React). This tool mimics a browser, **captures the same JSON** the page loads, and prints a clean table.

---

## Features

- Top images by **Pulls**
- Top images by **Stars**
- **Latest** N images by *Last Updated*
- Exact table headers: **Name | Owner | Pulls | Stars | Last Updated | URL**
- JSON output option (includes `name`, `owner`, `pulls`, `stars`, `last_updated`, `url`)
- DOM-scrape fallback if the search JSON changes

---

## Requirements

- Python **3.8+** (tested on 3.13 as well)
- Packages: `playwright`, `beautifulsoup4`

Install dependencies:
```bash
pip install playwright beautifulsoup4
python -m playwright install chromium
```

> If Chromium installation is blocked in your environment, try WebKit:
> ```bash
> python -m playwright install webkit
> ```
> and replace `p.chromium.launch(...)` with `p.webkit.launch(...)` inside the script.

---

## Usage

1) Save the script as **`dockerhub_top_images.py`** (or use your existing file).  
2) Run from your shell:

```bash
python dockerhub_top_images.py --top 25 --latest 10 --out table
```

**Arguments**

| Flag | Description | Default |
|---|---|---|
| `--top` | Number of rows for Top by Pulls and Top by Stars | `25` |
| `--latest` | Number of rows for Latest by Last Updated | `10` |
| `--out` | Output format: `table` or `json` | `table` |

**JSON example**
```bash
python dockerhub_top_images.py --top 25 --latest 10 --out json > results.json
```

---

## Output

### Table (headers are fixed as requested)

```
Top 25 images by pulls
======================
Name                             Owner                    Pulls      Stars  Last Updated           URL
---------------------------------------------------------------------------------------------------------------
nginx                            library                  1B+        19000  2025-10-07T12:34:56Z   https://hub.docker.com/r/library/nginx
redis                            library                  1B+        12000  2025-10-06T10:20:30Z   https://hub.docker.com/r/library/redis
...
```

### JSON (truncated illustration)
```json
{
  "top_by_pulls": [
    {
      "name": "nginx",
      "owner": "library",
      "pulls": "1B+",
      "stars": 19000,
      "last_updated": "2025-10-07T12:34:56Z",
      "url": "https://hub.docker.com/r/library/nginx"
    }
  ],
  "top_by_stars": [ ... ],
  "latest": [ ... ]
}
```

> **Note:** Pull counts are displayed in the same compact format the UI shows (e.g., `10M+`, `1B+`) when provided; if the search JSON returns an integer, it is formatted with thousands separators.

---

## How it works (high level)

1. Launches a headless browser with Playwright (Chromium by default).  
2. Navigates to `https://hub.docker.com/search?q=&type=image&order=desc&sort=<pulls|stars|updated_at>&page=<n>`.  
3. **Listens for the page’s XHR/Fetch responses** and parses the search JSON payload used by the UI.  
4. If that payload shape changes, it **falls back** to a tolerant DOM scrape of `/r/<owner>/<repo>` cards.  
5. Prints a table with **Name | Owner | Pulls | Stars | Last Updated | URL**, or JSON if requested.

---

## Troubleshooting

- **Empty results / timeouts**  
  - Ensure Chromium is installed: `python -m playwright install chromium`  
  - Try headful mode (debug): change `launch(headless=True)` → `launch(headless=False)` to watch the page load.  
  - Some corporate proxies block Hub XHR; test on a different network/VPN.  
  - Switch engine to WebKit: replace `p.chromium.launch(...)` with `p.webkit.launch(...)`.

- **AttributeError: 'Page' object has no attribute 'off'**  
  The Python API uses `page.remove_listener("response", handler)` instead of `.off(...)`. The provided script already uses the correct method.

- **CI containers**  
  If you run in CI or Docker, Playwright may require extra system packages (fonts, shared libs). See Playwright’s docs for the base image or install script.

---

## Alternatives (API-only, scoped)

Docker Hub’s public API supports **namespace-scoped** sorting (e.g., official images under `library`) but not a **global** “top across all Hub” index. If you’d like an API-only variant that aggregates multiple namespaces (e.g., `library`, `bitnami`, `grafana`, `elastic`), let me know and I can include a companion script.

---

## License

MIT License © 2025 **@hlosukwakha**

---

## Disclaimer

This tool automates a browser to view publicly available Hub search pages, similarly to a user. Use responsibly and respect Docker Hub’s terms of service. Behavior of the search UI and underlying JSON endpoints may change over time.
