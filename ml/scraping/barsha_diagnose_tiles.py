from playwright.sync_api import sync_playwright

BASE_URL = "https://www.barsha.com.tn"
USER_AGENT = "Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)"


def dismiss_overlays(page):
    page.evaluate("""
        document.querySelectorAll('.welcome-popup-backdrop, [class*="popup" i], [class*="modal" i]')
            .forEach(el => el.remove());
    """)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent=USER_AGENT)

    for section in ["Femme", "Homme"]:
        page.goto(f"{BASE_URL}/fr/categorie/{section}", wait_until="load", timeout=30000)
        page.wait_for_timeout(3000)
        dismiss_overlays(page)

        names = page.eval_on_selector_all(
            "div.category-item .name, div.category-item p",
            "els => els.map(e => e.textContent.trim())",
        )
        n_tiles = len(page.query_selector_all("div.category-item"))
        print(f"\n=== {section}: {n_tiles} tiles, names: {names} ===")

        for i in range(n_tiles):
            page.goto(f"{BASE_URL}/fr/categorie/{section}", wait_until="load", timeout=30000)
            page.wait_for_timeout(2000)
            dismiss_overlays(page)

            tiles = page.query_selector_all("div.category-item")
            if i >= len(tiles):
                continue
            name = tiles[i].query_selector(".name, p")
            label = name.inner_text().strip() if name else "?"

            page.evaluate("el => el.click()", tiles[i])
            page.wait_for_timeout(2500)

            start_url = f"{BASE_URL}/fr/categorie/{section}"
            result = page.url if page.url != start_url else "(no navigation)"
            print(f"  [{i}] {label!r:25} -> {result}")

    browser.close()
