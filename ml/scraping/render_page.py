"""One-off inspector: renders a JS-heavy page with a real browser and dumps the
resulting DOM, so we can find the right CSS selectors before writing a scraper.

Usage: python render_page.py <url> <output.html>
"""

import sys

from playwright.sync_api import sync_playwright


def render(url: str, output_path: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent="Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)")
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)  # let any lazy content settle
        html = page.content()
        browser.close()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved rendered HTML ({len(html)} chars) to {output_path}")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
