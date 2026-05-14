"""
Crawl OSS documentation sites and return raw document dicts.
Uses BFS with link extraction to recursively discover pages.
"""

import logging
import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Seed paths per source — these are high-value entry points
SEED_PATHS = {
    "k8s": [
        "/docs/concepts/", "/docs/tasks/", "/docs/tutorials/",
        "/docs/reference/", "/docs/setup/",
    ],
    "docker": [
        "/get-started/", "/engine/", "/compose/", "/config/",
        "/network/", "/storage/",
    ],
    "terraform": [
        "/language/", "/cli/", "/internals/",
        "/registry/", "/cloud-docs/",
    ],
}


class PageParser(HTMLParser):
    """Extract title, text, and links from HTML."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.text_parts = []
        self.links: list[str] = []
        self._in_title = False
        self._in_skip = False  # skip script, style, nav, footer

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in ("script", "style", "nav", "footer"):
            self._in_skip = True
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith("#") and not href.startswith("javascript"):
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer"):
            self._in_skip = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_skip:
            return
        if self._in_title:
            self.title += data.strip()
        else:
            text = data.strip()
            if text and len(text) > 2:
                self.text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


async def fetch_page(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Fetch a single page, return text content or None on failure."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        # Only accept HTML
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            return None
        return resp.text
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return None


def crawl_docs(source_cfg: dict, limit: int = 200) -> list[dict]:
    """
    Crawl a documentation source using BFS with link extraction.
    Returns list of {"url": str, "title": str, "text": str, "source": str} dicts.
    """
    source_name = source_cfg["name"]
    base_url = source_cfg["base_url"].rstrip("/")
    source_key = source_cfg.get("key", source_name.lower().split()[0])
    base_domain = urlparse(base_url).netloc

    # Build seed URLs
    seed_paths = SEED_PATHS.get(source_key, ["/"])
    seed_urls = [base_url + p for p in seed_paths]

    docs = []
    seen_urls: set[str] = set()
    queue: list[str] = list(seed_urls)

    def should_crawl(url: str) -> bool:
        """Only crawl URLs under the same base domain/path."""
        parsed = urlparse(url)
        if parsed.netloc != base_domain:
            return False
        # Skip anchors, queries, non-doc paths
        path = parsed.path
        if not path or path == "/":
            return False
        if any(skip in path for skip in ["/search", "/feed", "/tag/", "/author/", "/page/"]):
            return False
        if not path.startswith(base_url.replace("https://", "").replace("http://", "").split("/", 1)[-1] if "/" in base_url else "/"):
            # Ensure the path starts with the docs prefix
            docs_prefix = urlparse(base_url).path or "/"
            if not path.startswith(docs_prefix):
                return False
        return True

    async def _crawl():
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=10),
            timeout=httpx.Timeout(30.0),
        ) as client:
            while queue and len(docs) < limit:
                # Pop next batch (up to 10 concurrent)
                batch_urls = []
                while queue and len(batch_urls) < 10:
                    url = queue.pop(0)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        batch_urls.append(url)

                if not batch_urls:
                    break

                # Fetch batch concurrently
                tasks = [fetch_page(client, url) for url in batch_urls]
                results = await asyncio.gather(*tasks)

                for url, html in zip(batch_urls, results):
                    if not html:
                        continue

                    parser = PageParser()
                    try:
                        parser.feed(html)
                    except Exception:
                        continue

                    text = parser.get_text()
                    if len(text) < 200:  # skip near-empty pages
                        continue

                    docs.append({
                        "url": url,
                        "title": parser.title or url,
                        "text": text,
                        "source": source_name,
                    })

                    # Extract and queue new links
                    for link in parser.links:
                        full_url = urljoin(url, link)
                        if full_url not in seen_urls and should_crawl(full_url):
                            queue.append(full_url)

                    if len(docs) >= limit:
                        break

                logger.info(f"  Crawled {len(docs)}/{limit} pages, {len(queue)} queued")

        return docs

    return asyncio.run(_crawl())
