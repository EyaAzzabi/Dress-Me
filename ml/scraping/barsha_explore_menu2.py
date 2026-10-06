from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent="Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)")
    page.goto("https://www.barsha.com.tn/fr/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    page.evaluate("""
        document.querySelectorAll('.welcome-popup-backdrop, [class*="popup" i], [class*="modal" i]')
            .forEach(el => el.remove());
    """)
    page.wait_for_timeout(500)

    el = page.get_by_text("POUR ELLE", exact=True).first
    el.click(force=True)
    page.wait_for_timeout(2000)
    print("URL after clicking POUR ELLE:", page.url)

    # dump any new leaf texts (submenu) that appeared
    candidates = page.eval_on_selector_all(
        "*",
        """els => els
            .filter(e => e.children.length === 0)
            .map(e => e.textContent.trim())
            .filter(t => t.length > 0 && t.length < 30)
        """,
    )
    with open("barsha_after_click.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(set(candidates))))

    browser.close()
