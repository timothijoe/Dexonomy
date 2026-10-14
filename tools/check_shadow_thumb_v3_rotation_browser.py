#!/usr/bin/env python3
"""Exercise camera controls, navigation and rapid loading with WebGL disabled."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from dexonomy.integrations.bench2dex.common import atomic_json


def check(root):
    root = Path(root).resolve(); data = json.loads((root / 'viewer.json').read_text())
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/google/chrome/chrome', headless=True,
                                    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-webgl', '--disable-webgl2'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto((root / 'index.html').as_uri())
        def ready(count=3):
            page.wait_for_function("count=>document.querySelectorAll('canvas').length===count&&document.querySelector('#loading').textContent===''", arg=count)
        def angles(yaw, pitch, roll, count=3):
            page.wait_for_function("a=>document.querySelectorAll('canvas').length===a[3]&&[...document.querySelectorAll('canvas')].every(c=>c.dataset.yaw===String(a[0])&&c.dataset.pitch===String(a[1])&&c.dataset.roll===String(a[2]))&&document.querySelector('#loading').textContent===''", arg=[yaw,pitch,roll,count])
        ready(); assert page.evaluate("document.createElement('canvas').getContext('webgl')===null")
        page.click('#yawPrevious'); angles(11,2,0)
        page.click('#yawNext'); angles(0,2,0)
        page.click('#pitchPrevious'); angles(0,1,0)
        page.click('#pitchPrevious'); angles(0,0,0)
        page.click('#pitchPrevious'); angles(0,0,0)
        page.click('#rollPrevious'); angles(0,0,11)
        page.click('#rollNext'); angles(0,0,0)
        page.evaluate("()=>{for(const [id,value] of [['yawRange',5],['pitchRange',4],['rollRange',3]]){const e=document.getElementById(id);e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}))}}")
        angles(5,4,3)
        page.click('#reset'); angles(0,2,0)
        page.select_option('#phase','all'); angles(0,2,0,9)
        for mode in ['hand','scene']:
            page.click('#'+mode)
            page.wait_for_function("mode=>document.querySelectorAll('canvas').length===9&&[...document.querySelectorAll('canvas')].every(c=>c.dataset.path.includes('_'+mode+'_'))&&document.querySelector('#loading').textContent===''",arg=mode)
        box = page.locator('canvas').first.bounding_box()
        page.mouse.move(box['x']+100,box['y']+100);page.mouse.down()
        page.mouse.move(box['x']+40,box['y']+55,steps=4);angles(3,3,0,9);page.mouse.up()
        # Rapid state updates must resolve to the latest frame, for all panels.
        page.evaluate("()=>{for(const value of [1,6,2,9]){const e=document.getElementById('yawRange');e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}))}}")
        angles(9,3,0,9)
        page.select_option('#phase','grasp');ready()
        page.click('#reset');angles(0,2,0)
        # Check each alias entry in every phase/mode at the baseline view.
        for entry in data['entries']:
            page.select_option('#asset',entry['asset']);page.select_option('#grasp',entry['entryId'])
            for phase in ['pregrasp','grasp','squeeze']:
                page.select_option('#phase',phase)
                for mode in ['scene','hand']:
                    page.click('#'+mode)
                    page.wait_for_function("a=>document.querySelectorAll('canvas').length===3&&[...document.querySelectorAll('canvas')].every(c=>c.dataset.phase===a[0]&&c.dataset.path.includes('/'+a[1]+'/')&&c.dataset.path.includes('_'+a[2]+'_'))&&document.querySelector('#loading').textContent===''",arg=[phase,entry['caseId'],mode])
        if any(e['asset']=='056_tennis_ball' for e in data['entries']):page.select_option('#asset','056_tennis_ball')
        page.select_option('#phase','grasp');ready();page.screenshot(path=str(root/'rotation_checked.png'),full_page=True)
        page.set_viewport_size({'width':430,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors
        browser.close()
    report = {'webgl_disabled': True, 'alias_entries_checked': len(data['entries']),
              'baseline_phase_mode_combinations': len(data['entries'])*6,
              'three_axis_buttons_sliders_drag_reset_passed': True,
              'wrapping_pitch_clamping_and_latest_request_passed': True,
              'all_phases_and_mobile_passed': True, 'page_errors': errors}
    atomic_json(root/'browser_check.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/rotation'))
    args=parser.parse_args();print(json.dumps(check(args.output),ensure_ascii=False,indent=2))
