from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent="Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)")
    page.goto("https://www.barsha.com.tn/fr/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    # dismiss any welcome/newsletter popup overlay first
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.evaluate("""
        document.querySelectorAll('.welcome-popup-backdrop, [class*="popup" i], [class*="modal" i]')
            .forEach(el => el.remove());
    """)
    page.wait_for_timeout(500)

    toggler = page.query_selector("button.navbar-toggler")
    if toggler:
        toggler.click(force=True)
        page.wait_for_timeout(1500)

    # find any element (not just <a>) whose text looks like a top-level category
    candidates = page.eval_on_selector_all(
        "*",
        """els => els
            .filter(e => e.children.length === 0)
            .map(e => e.textContent.trim())
            .filter(t => t.length > 0 && t.length < 30)
        """,
    )
    with open("barsha_texts.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(set(candidates))))
    print(f"{len(set(candidates))} unique leaf text nodes saved to barsha_texts.txt")

    links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    unique_links = sorted(set(links))
    with open("barsha_menu_links.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(unique_links))
    print(f"{len(unique_links)} unique links saved to barsha_menu_links.txt")

    browser.close()
