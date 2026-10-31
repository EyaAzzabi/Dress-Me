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

    before = len(page.query_selector_all("div.card"))
    print("cards before scroll:", before)

    for i in range(6):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1000)

    after = len(page.query_selector_all("div.card"))
    print("cards after scroll:", after)

    buttons = page.eval_on_selector_all(
        "button, a",
        "els => els.map(e => e.textContent.trim()).filter(t => t.length > 0 && t.length < 30)",
    )
    print("buttons/links text:", sorted(set(buttons)))

    browser.close()
