from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent="Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)")
    page.goto("https://www.barsha.com.tn/fr/categorie/Femme", wait_until="load", timeout=30000)
    page.wait_for_timeout(4000)
    page.evaluate("""
        document.querySelectorAll('.welcome-popup-backdrop, [class*="popup" i], [class*="modal" i]')
            .forEach(el => el.remove());
    """)
    page.wait_for_timeout(300)

    tile = page.query_selector("div.category-item")
    page.evaluate("el => el.click()", tile)
    page.wait_for_timeout(3000)
    print("URL after clicking a category-item:", page.url)

    counts = page.eval_on_selector_all(
        "[class]",
        """els => {
            const map = {};
            for (const e of els) {
                const key = e.tagName + '.' + e.className;
                map[key] = (map[key] || 0) + 1;
            }
            return Object.entries(map).filter(([k,v]) => v >= 3).sort((a,b) => b[1]-a[1]).slice(0, 25);
        }""",
    )
    for k, v in counts:
        print(v, k)

    with open("barsha_subcat_page.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    browser.close()
