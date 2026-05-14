"""
Crawl OSS documentation sites and return raw document dicts.
"""

import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Pages to fetch per source — these are high-value entry points
SEED_PATHS = {
    "k8s": [
        "/docs/concepts/", "/docs/tasks/", "/docs/tutorials/",
        "/docs/reference/", "/docs/setup/", "/docs/contribute/",
    ],
    "docker": [
        "/get-started/", "/engine/", "/compose/", "/config/",
        "/network/", "/storage/",
    ],
    "terraform": [
        "/language/", "/cli/", "/internals/", "/plugin/",
        "/registry/", "/cloud-docs/",
    ],
}


async def fetch_page(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Fetch a single page, return text content or None on failure."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return None


def crawl_docs(source_cfg: dict, limit: int = 200) -> list[dict]:
    """
    Crawl a documentation source synchronously.
    Returns list of {"url": str, "title": str, "text": str, "source": str} dicts.
    """
    import asyncio
    import re
    from html.parser import HTMLParser

    class TitleTextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""
            self.text_parts = []
            self.in_title = False
            self.in_script = False
            self.in_style = False
            self.current_tag = ""

        def handle_starttag(self, tag, attrs):
            self.current_tag = tag
            if tag in ("script", "style"):
                self.in_script = True
            elif tag == "title":
                self.in_title = True

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.in_script = False
            elif tag == "title":
                self.in_title = False
            self.current_tag = ""

        def handle_data(self, data):
            if self.in_script or self.in_style:
                return
            if self.in_title:
                self.title += data.strip()
            else:
                text = data.strip()
                if text:
                    self.text_parts.append(text)

        def get_text(self):
            return " ".join(self.text_parts)

    source_name = source_cfg["name"]
    base_url = source_cfg["base_url"]
    source_key = source_cfg.get("key", source_name.lower().split()[0])

    # Build seed URLs from known paths
    seed_paths = SEED_PATHS.get(source_key, ["/"])
    seed_urls = [base_url.rstrip("/") + p for p in seed_paths]

    docs = []
    seen_urls = set()

    async def _crawl():
        async with httpx.AsyncClient() as client:
            # Fetch seed pages
            tasks = [fetch_page(client, url) for url in seed_urls[:limit]]
            results = await asyncio.gather(*tasks)

            for url, html in zip(seed_urls[:limit], results):
                if not html or url in seen_urls:
                    continue
                seen_urls.add(url)

                extractor = TitleTextExtractor()
                try:
                    extractor.feed(html)
                except Exception:
                    continue

                text = extractor.get_text()
                if len(text) < 100:  # skip near-empty pages
                    continue

                docs.append({
                    "url": url,
                    "title": extractor.title or url,
                    "text": text,
                    "source": source_name,
                })

        return docs

    return asyncio.run(_crawl())
