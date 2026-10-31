from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent="Mozilla/5.0 (compatible; DressMe-research-bot/1.0; +educational project)")
    page.goto("https://www.barsha.com.tn/fr/tn/5-chaussures-femme", wait_until="load", timeout=30000)
    page.wait_for_timeout(3000)
    page.evaluate("""
        document.querySelectorAll('.welcome-popup-backdrop, [class*="popup" i], [class*="modal" i]')
            .forEach(el => el.remove());
    """)

    voir_tout = page.get_by_text("Voir tout", exact=True).first
    voir_tout.evaluate("el => el.click()")
    page.wait_for_timeout(3000)
    print("URL after 'Voir tout':", page.url)
    print("cards:", len(page.query_selector_all("div.card")))

    # try scrolling now too
    for i in range(6):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1000)
    print("cards after scroll:", len(page.query_selector_all("div.card")))

    browser.close()
