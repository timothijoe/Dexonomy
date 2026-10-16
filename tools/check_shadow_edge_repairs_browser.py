#!/usr/bin/env python3
"""Exercise the four edge-repair rotation comparisons in Chromium."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('output/shadow_wuji_v4/edge_repair_2026-10-15/rotation').resolve();data=json.loads((root/'viewer.json').read_text());errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/opt/google/chrome/chrome',headless=True,args=['--no-sandbox','--disable-webgl'])
 page=b.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto((root/'index.html').as_uri())
 def ready(n=2):page.wait_for_function("n=>document.querySelectorAll('canvas').length===n&&document.querySelector('#loading').textContent===''",arg=n)
 ready();page.click('#yawNext');ready();page.click('#pitchNext');ready();page.click('#rollNext');ready()
 page.locator('#history summary').click();ready(3);assert '原 V3 基线' in page.locator('#panels').inner_text();assert '历史 V2' not in page.locator('#panels').inner_text()
 page.select_option('#phase','all');ready(9)
 for e in data['entries']:
  page.select_option('#asset',e['asset']);page.select_option('#grasp',e['entryId']);ready(9)
  for mode in ['scene','hand']:
   page.click('#'+mode);page.wait_for_function("m=>document.querySelector('#loading').textContent===''&&[...document.querySelectorAll('canvas')].every(c=>c.dataset.path.includes('_'+m+'_'))",arg=mode)
  assert e['selectedLabel'] in page.locator('#panels').inner_text()
 page.select_option('#asset',data['entries'][0]['asset']);page.select_option('#phase','grasp');ready(3);page.click('#scene');ready(3)
 page.locator('#history summary').click();ready();page.screenshot(path=str(root/'review_checked.png'),full_page=True)
 page.set_viewport_size({'width':430,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors;b.close()
report={'cases_checked':len(data['entries']),'default_two_columns_and_original_v3_comparison':True,'proposal_rejection_labels':True,'camera_controls_and_phase_mode_navigation':True,'mobile_passed':True,'page_errors':errors}
(root/'browser_check.json').write_text(json.dumps(report,indent=2));print(report)
