#!/usr/bin/env python3
"""Check every type's overview images and representative rotation interactions."""
import argparse
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright


def check(root):
    root=Path(root).resolve();view=root/'review';data=json.loads((view/'review.json').read_text())
    assets=list(dict.fromkeys(e['asset'] for e in data['entries']));errors=[];comparisons=0
    assert data['completedCases']==data['uniqueCases']==len(data['entries'])
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/opt/google/chrome/chrome',headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage','--disable-webgl','--disable-webgl2'])
        page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((view/'index.html').as_uri())
        def loaded(n):
            page.evaluate("()=>{for(const h of document.querySelectorAll('#cards .placeholder[data-path]'))h.loadComparison()}")
            page.wait_for_function("n=>document.querySelectorAll('#cards canvas').length===n*6&&!document.querySelector('#cards .placeholder')",arg=n,timeout=60000)
        assert page.locator('#cameraControls').is_visible()
        for asset in assets:
            page.select_option('#asset',asset);n=sum(e['asset']==asset for e in data['entries'])
            assert page.locator('article').count()==n
            for mode in ['#withObject','#handOnly']:
                page.click(mode);loaded(n);comparisons+=n
        page.locator('article canvas').first.click();assert page.locator('#large canvas').count()==6
        page.click('#modalyawNext')
        page.wait_for_function("()=>[...document.querySelectorAll('#large canvas')].every(c=>c.dataset.yaw==='1')")
        page.keyboard.press('Escape')
        page.locator('#history summary').click()
        page.wait_for_function("()=>document.querySelectorAll('#cards canvas[data-role=\"1\"]').length>0")
        page.locator('#history summary').click()
        page.set_viewport_size({'width':430,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(view/'review_checked.png'),full_page=True)
        page.goto((view/'rotation/index.html').as_uri())
        def ready(n=2):page.wait_for_function("n=>document.querySelectorAll('canvas').length===n&&document.querySelector('#loading').textContent===''",arg=n)
        ready();assert page.evaluate("document.createElement('canvas').getContext('webgl')===null")
        chosen={}
        for entry in data['entries']:
            chosen.setdefault('asset:'+entry['asset'],entry);chosen.setdefault('category:'+entry['category'],entry)
        sampled={e['asset']+'::'+e['category']:e for e in chosen.values()}
        for eid,entry in sampled.items():
            page.select_option('#asset',entry['asset']);page.select_option('#grasp',eid)
            for phase in ['pregrasp','grasp','squeeze']:
                page.select_option('#phase',phase)
                for mode in ['scene','hand']:
                    page.click('#'+mode)
                    cid=Path(entry['result']).parent.name
                    page.wait_for_function("a=>document.querySelectorAll('canvas').length===2&&[...document.querySelectorAll('canvas')].every(c=>c.dataset.phase===a[0]&&c.dataset.path.includes('/'+a[1]+'/')&&c.dataset.path.includes('_'+a[2]+'_'))&&document.querySelector('#loading').textContent===''",arg=[phase,cid,mode])
        page.click('#yawNext');ready();page.click('#pitchNext');ready();page.click('#rollNext');ready()
        page.select_option('#phase','all');ready(6);page.locator('#history summary').click();ready(9)
        assert page.locator('canvas[data-role="1"]').count()==3
        page.locator('#history summary').click();ready(6);page.click('#reset');ready(6)
        page.screenshot(path=str(view/'rotation/rotation_checked.png'),full_page=True)
        page.set_viewport_size({'width':430,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors;browser.close()
    report={'models_checked':len(assets),'type_overviews_checked':len(data['entries']),
        'overview_comparisons_in_two_modes':comparisons,'rotation_representative_entries':len(sampled),
        'rotation_phase_mode_combinations':len(sampled)*6,'all_models_and_taxonomy_categories_represented':True,
        'default_history_axes_zoom_mobile_and_webgl_disabled_passed':True,'page_errors':errors}
    (root/'browser_check.json').write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    p.add_argument('--wait',action='store_true');a=p.parse_args()
    if a.wait:
        while True:
            progress=a.output/'progress.json'
            if progress.is_file() and json.loads(progress.read_text()).get('stage')=='complete':break
            time.sleep(15)
    print(json.dumps(check(a.output),ensure_ascii=False,indent=2),flush=True)
