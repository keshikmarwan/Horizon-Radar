from playwright.sync_api import sync_playwright


def test_connector_selectors_with_playwright():
    html = """
    <html><body>
      <article><h2>Draft work programme update</h2><a href='x.pdf'>PDF</a></article>
      <article><h2>General news</h2></article>
    </body></html>
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        draft_titles = page.locator('article h2').all_text_contents()
        browser.close()

    assert 'Draft work programme update' in draft_titles
