"""Load the real game in a headless browser and exercise cookie_auto.js.

    uv run tests/browser_smoke.py
"""
import os, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = open(os.path.join(ROOT, 'cookie_auto.js')).read()

def main():
    with sync_playwright() as p:
        try:
            browser = p.firefox.launch(headless=True)
        except Exception as e:
            print('firefox failed:', e)
            browser = p.chromium.launch(headless=True, executable_path='/snap/bin/chromium')
        page = browser.new_page()
        errors = []
        page.on('console', lambda m: print('console:', m.text) if ('CCAuto' in m.text or m.type == 'error') else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('https://orteil.dashnet.org/cookieclicker/', timeout=120000)
        page.wait_for_function('window.Game && Game.ready', timeout=120000)
        print('game version', page.evaluate('Game.version'))
        page.evaluate(sys.argv[1] if len(sys.argv) > 1 else '0')
        page.evaluate(SCRIPT)
        time.sleep(float(os.environ.get('WAIT', 20)))
        print(page.evaluate("document.getElementById('ccautoPanel') ? document.getElementById('ccautoPanel').innerText : 'no panel'"))
        print('cookies', page.evaluate('Beautify(Game.cookies)'), 'clicks', page.evaluate('Game.cookieClicks'))
        print('page errors:', errors)
        browser.close()

if __name__ == '__main__':
    main()
