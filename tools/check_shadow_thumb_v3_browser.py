#!/usr/bin/env python3
"""Check the offline V3 review in Chromium, including two-column defaults and optional V2 history."""
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
    def loaded(page, cards, roles=2):
        page.evaluate("()=>{for(const h of document.querySelectorAll('#cards .placeholder[data-path]'))h.loadComparison()}")
        page.wait_for_function("a=>document.querySelectorAll('#cards canvas').length===a[0]*3*a[1]&&!document.querySelector('#cards .placeholder')", arg=[cards,roles])
        expected_roles=['0','2'] if roles==2 else ['0','1','2']
        assert page.locator('#cards canvas').evaluate_all("cs=>[...new Set(cs.map(c=>c.dataset.role))]") == expected_roles
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
                loaded(page, expected)
                image_count += expected
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
        loaded(page,4)
        assert not page.locator('#history').evaluate('e=>e.open')
        page.locator('article canvas').first.click()
        assert page.locator('#large canvas').count()==6
        assert page.locator('#modal').evaluate("e=>e.classList.contains('open')")
        page.keyboard.press('Escape')
        assert not page.locator('#modal').evaluate("e=>e.classList.contains('open')")
        page.locator('#history summary').click();loaded(page,4,3)
        page.locator('article canvas').first.click()
        assert page.locator('#large canvas').count()==9
        page.keyboard.press('Escape')
        page.click('#withObject');loaded(page,4,3)
        assert page.locator('#cards canvas').evaluate_all("cs=>cs.every(c=>!c.dataset.path.includes('hand_only')&&!c.dataset.path.includes('_hand_'))")
        page.locator('#history summary').click();loaded(page,4)
        if data.get('camera'):
            assert page.locator('#cameraControls').is_visible()
            def angles(yaw,pitch,roll,selector='#cards canvas'):
                page.wait_for_function("a=>document.querySelectorAll(a[3]).length>0&&[...document.querySelectorAll(a[3])].every(c=>c.dataset.yaw===String(a[0])&&c.dataset.pitch===String(a[1])&&c.dataset.roll===String(a[2]))",arg=[yaw,pitch,roll,selector])
            page.click('#yawPrevious');loaded(page,4);angles(11,2,0)
            page.click('#pitchNext');loaded(page,4);angles(11,3,0)
            page.click('#rollNext');loaded(page,4);angles(11,3,1)
            page.locator('article canvas').first.click()
            assert page.locator('#modalCameraControls').is_visible()
            page.click('#modalrollNext');angles(11,3,2,'#large canvas')
            page.click('#modalpitchPrevious');angles(11,2,2,'#large canvas')
            page.click('#modalyawNext');angles(0,2,2,'#large canvas')
            page.keyboard.press('Escape');loaded(page,4);angles(0,2,2)
            page.click('#rollPrevious');page.click('#rollPrevious');loaded(page,4);angles(0,2,0)
        page.screenshot(path=str(root / 'review_checked.png'), full_page=True)
        page.set_viewport_size({'width': 430, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        retained=next(e for e in data['entries'] if e['selectedVersion']=='v2_retained')
        page.select_option('#asset',retained['asset']);page.select_option('#version','v2_retained')
        expected=sum(e['asset']==retained['asset'] and e['selectedVersion']=='v2_retained' for e in data['entries'])
        loaded(page,expected)
        assert page.locator('#cards').inner_text().count('最终 Wuji（沿用 V2）')==expected*3
        assert '动力学未验证' in page.locator('#cards').inner_text()
        assert not errors
        browser.close()
    report = {'assets_checked': len(assets), 'coverage_cards': len(data['entries']),
              'image_decodes_in_two_modes': image_count, 'version_filter_counts': dict(versions),
              'status_filter_counts': dict(statuses), 'search_zoom_escape_and_mobile_passed': True,
              'default_two_columns_and_expandable_v2_history_passed': True,
              'overview_and_zoom_camera_controls_passed': bool(data.get('camera')),
              'retained_v2_provenance_and_physical_status_passed': True,
              'page_errors': errors}
    atomic_json(root / 'browser_check.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    args = parser.parse_args()
    print(json.dumps(check(args.batch), ensure_ascii=False, indent=2))
