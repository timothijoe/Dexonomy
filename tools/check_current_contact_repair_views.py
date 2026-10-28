#!/usr/bin/env python3
"""Validate every new frame and exercise selected/proposal review navigation."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt
from dexonomy.integrations.bench2dex.shadow_batch import digest
from dexonomy.integrations.bench2dex.thumb_v3_rotation import frame_name
from tools.repair_current_shadow_contacts import verify,DEFAULT
from tools.check_current_shadow_grasp_types_browser import check as full_browser


def selection(root):
    root=Path(root);view=root/'review';data=json.loads((view/'review.json').read_text())
    s=json.loads((root/'summary.json').read_text());repairs={r['case_id']:r for r in s['rows']};receipts=[]
    assert len(data['entries'])==len({(e['asset'],e['category']) for e in data['entries']})==1164
    for e in data['entries']:
        cid=e['rotationCase'];folder=(view/e['result']).parent;posture=view/e['postures']
        frame=json.loads((view/'rotation/frames'/cid/'receipt.json').read_text())
        assert frame['row']['postures']['sha256']==file_receipt(posture)['sha256'],cid
        repair=repairs.get(cid);accepted=bool(repair and repair['adopted'])
        assert (e['selectedVersion']=='contact_repair')==accepted
        r=json.loads((view/e['result']).read_text())
        assert r['physical_passed'] is None and r['full_task_passed'] is None
        if accepted:
            assert r['schema_version']=='current_contact_repair_selected_v1'
            assert 'selected_thumb' not in r and 'proposed_thumb' not in r
            verify([r['comparison_baseline'],r['repair_report'],r['fresh_audit']])
            assert not e['requiredPatchDrift'] and r['selected_quality']['passed'] and r['selected_natural']['passed']
            assert file_receipt(posture)['sha256']==file_receipt(Path(repair['proposal_folder'])/'postures.npz')['sha256']
        receipts.extend([file_receipt(view/e['result']),file_receipt(posture)])
    report={'model_category_pairs':1164,'adopted':s['adopted'],'all_selected_poses_bound_to_displayed_frames':True,
        'selected_reports_contain_only_recomputed_metrics':True,'selected_inputs':receipts}
    atomic_json(root/'selection_check.json',report);return {k:v for k,v in report.items() if k!='selected_inputs'}


def frames(root):
    root=Path(root);summary=json.loads((root/'summary.json').read_text());config={'width':480,'height':360,'quality':76}
    names={frame_name(p,m,i,j) for p in ['pregrasp','grasp','squeeze'] for m in ['scene','hand'] for i in range(5) for j in range(12)}
    def inspect(row):
        folder=root/'proposals/frames'/row['case_id'];saved=json.loads((folder/'receipt.json').read_text())
        p=Path(row['proposal_folder']);j={'case_id':row['case_id'],'result':file_receipt(p/'result.json'),'postures':file_receipt(p/'postures.npz')}
        expected=digest({'job':j,'config':config,'renderer':file_receipt(Path('dexonomy/integrations/bench2dex/thumb_v3_rotation.py'))})
        assert saved['identity']==expected and saved['row']['postures']==j['postures']
        assert {p.name for p in folder.glob('*.webp')}==names
        verify([{'path':str(folder/a['path']),'sha256':a['sha256']} for a in saved['artifacts']])
        for name in names:
            with Image.open(folder/name) as im:assert im.size==(1440,360)
        for phase in ['pregrasp','grasp','squeeze']:
            for mode in ['scene','hand']:
                with Image.open(folder/frame_name(phase,mode,2,0)) as im:
                    im.load();assert im.size==(1440,360);a=np.asarray(im)
                    for role in range(3):assert a[:,role*480:(role+1)*480].std()>2
        return len(names)
    with ThreadPoolExecutor(max_workers=8) as ex:n=sum(ex.map(inspect,summary['rows']))
    report={'new_cases':len(summary['rows']),'new_frames_hashed':n,
        'frame_headers_checked':n,'three_role_frames_fully_decoded':6*len(summary['rows']),
        'all_camera_grid_names_and_pose_bindings_verified':True}
    atomic_json(root/'frame_check.json',report);return report


def browser(root):
    root=Path(root).resolve();full=full_browser(root)
    view=root/'review';data=json.loads((view/'review.json').read_text());summary=json.loads((root/'summary.json').read_text())
    adopted={r['case_id'] for r in summary['rows'] if r['adopted']};errors=[]
    remaining=sum(e['status']=='kinematic_candidate' and e['requiredPatchDrift'] for e in data['entries'])
    proposal_data=json.loads((view/'repair_proposals/viewer.json').read_text())
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path='/opt/google/chrome/chrome',headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage','--disable-webgl','--disable-webgl2'])
        page=b.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((view/'index.html').as_uri());page.select_option('#asset','');page.select_option('#version','contact_repair')
        assert page.locator('article').count()==len(adopted)
        page.select_option('#version','');page.select_option('#status','kinematic_candidate');page.select_option('#contact','required_drift')
        assert page.locator('article').count()==remaining
        entry=next(e for e in data['entries'] if e['selectedVersion']=='contact_repair')
        page.select_option('#contact','');page.select_option('#asset',entry['asset']);page.select_option('#category',entry['category'])
        page.evaluate("()=>{for(const h of document.querySelectorAll('#cards .placeholder[data-path]'))h.loadComparison()}")
        page.wait_for_function("()=>document.querySelectorAll('#cards canvas').length===6&&!document.querySelector('#cards .placeholder')")
        assert '接触修复' in page.locator('article figcaption').last.inner_text()
        page.locator('#history summary').click()
        page.wait_for_function("()=>document.querySelectorAll('#cards canvas').length===9")
        assert '修复前 Wuji' in page.locator('#cards').inner_text()
        assert '历史 V2' not in page.locator('#cards').inner_text()
        for anchor in page.locator('article .links a').all():
            href=anchor.get_attribute('href').split('#')[0].split('?')[0]
            assert (view/href).is_file(),href
        page.goto((view/'repair_proposals/index.html').as_uri());page.select_option('#phase','all')
        def ready(cid,mode,n):
            page.wait_for_function("a=>document.querySelector('#loading').textContent===''&&document.querySelectorAll('canvas').length===a[2]&&[...document.querySelectorAll('canvas')].every(c=>c.dataset.path.includes('/'+a[0]+'/')&&c.dataset.path.includes('_'+a[1]+'_'))",arg=[cid,mode,n])
        for e in proposal_data['entries']:
            page.select_option('#asset',e['asset']);page.select_option('#grasp',e['entryId'])
            for mode in ['scene','hand']:
                page.click('#'+mode);ready(e['caseId'],mode,6)
            assert e['selectedLabel'] in page.locator('#panels').inner_text()
        page.locator('#history summary').click();ready(e['caseId'],'hand',9)
        assert '修复前 Wuji' in page.locator('#panels').inner_text()
        page.click('#yawNext');page.click('#pitchNext');page.click('#rollNext');ready(e['caseId'],'hand',9)
        page.wait_for_function("()=>[...document.querySelectorAll('canvas')].every(c=>c.dataset.yaw==='1'&&c.dataset.pitch==='3'&&c.dataset.roll==='1')")
        page.screenshot(path=str(view/'repair_proposals/checked.png'),full_page=True)
        page.set_viewport_size({'width':430,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors;b.close()
    report={'full_review':full,'adopted_filter_verified':len(adopted),'remaining_drift_filter_verified':remaining,
        'proposal_entries_checked':len(proposal_data['entries']),'proposal_three_phase_mode_comparisons':len(proposal_data['entries'])*6,
        'before_after_labels_actual_links_axes_history_mobile_verified':True,'page_errors':errors}
    atomic_json(root/'browser_check.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--frames-only',action='store_true');p.add_argument('--browser-only',action='store_true');a=p.parse_args()
    if not a.browser_only:
        print(json.dumps(selection(a.output),indent=2),flush=True)
        print(json.dumps(frames(a.output),indent=2),flush=True)
    if not a.frames_only:print(json.dumps(browser(a.output),indent=2),flush=True)
