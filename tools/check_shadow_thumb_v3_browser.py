#!/usr/bin/env python3
"""Check the offline V3 review in Chromium, including every asset's images."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from dexonomy.integrations.bench2dex.common import atomic_json


def check(root):
    root = Path(root).resolve()
    data = json.loads((root / 'review.json').read_text())
    if data['completedCases'] != data['uniqueCases']: raise ValueError('Review batch is incomplete')
    versions = Counter(e['selectedVersion'] for e in data['entries'])
    assets = list(dict.fromkeys(e['asset'] for e in data['entries']))
    errors, image_count = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/google/chrome/chrome',
                                    headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto((root / 'index.html').as_uri(), wait_until='load')
        assert page.locator('article').count() == len(data['entries'])
        for asset in assets:
            page.select_option('#asset', asset)
            expected = sum(e['asset'] == asset for e in data['entries'])
            assert page.locator('article').count() == expected
            for mode in ['#withObject', '#handOnly']:
                page.click(mode)
                decoded = page.evaluate("""async () => {
                  const images = [...document.querySelectorAll('article img')];
                  await Promise.all(images.map(image => {image.loading='eager'; return image.decode()}));
                  return images.filter(image=>image.naturalWidth>0&&image.naturalHeight>0).length;
                }""")
                assert decoded == expected
                image_count += decoded
        page.select_option('#asset', '')
        for version, count in versions.items():
            page.select_option('#version', version)
            assert page.locator('article').count() == count
        page.select_option('#version', '')
        statuses = Counter(e['status'] for e in data['entries'])
        for status, count in statuses.items():
            page.select_option('#status', status)
            assert page.locator('article').count() == count
        page.select_option('#status', '')
        page.fill('#search', '221_pen')
        assert page.locator('article').count() == sum(e['asset'] == '221_pen' for e in data['entries'])
        page.fill('#search', '')
        page.select_option('#asset', '056_tennis_ball')
        page.click('#handOnly')
        page.locator('article img').first.click()
        assert page.locator('#modal').evaluate("e=>e.classList.contains('open')")
        page.keyboard.press('Escape')
        assert not page.locator('#modal').evaluate("e=>e.classList.contains('open')")
        page.screenshot(path=str(root / 'review_checked.png'), full_page=True)
        page.set_viewport_size({'width': 430, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors
        browser.close()
    report = {'assets_checked': len(assets), 'coverage_cards': len(data['entries']),
              'image_decodes_in_two_modes': image_count, 'version_filter_counts': dict(versions),
              'status_filter_counts': dict(statuses), 'search_zoom_escape_and_mobile_passed': True,
              'page_errors': errors}
    atomic_json(root / 'browser_check.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    args = parser.parse_args()
    print(json.dumps(check(args.batch), ensure_ascii=False, indent=2))
