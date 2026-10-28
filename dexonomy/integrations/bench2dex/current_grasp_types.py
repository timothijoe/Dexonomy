"""Complete category coverage for existing source meshes using frozen optimizers."""
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing
from pathlib import Path
from time import monotonic

import numpy as np
import trimesh

from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json,file_receipt,sha256
from .shadow_batch import (digest,model_resources,verify_completed,verify_plan,job_identity,
                          _run_job,summarize)
from .thumb_v2_batch import prepare_v2,verify_v2,identity as v2_identity,_run as run_v2_case,summary as v2_summary
from .thumb_v3_batch import prepare_v3,verify_v3,identity as v3_identity,run_case as run_v3_case,summary as v3_summary

PARENTS=(Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'),
         Path('output/shadow_wuji_v4/expansion_pilot_2026-10-15/final'))
INVENTORY=Path('output/shadow_wuji_v4/expansion_inventory_2026-10-15/inventory.json')
TARGET=Path('output/bench2dex_v1/models/right/hand.xml')
CONFIGS={'v1':Path('configs/bench2dex/shadow_retarget_batch.yaml'),
         'v2':Path('configs/bench2dex/shadow_thumb_v2.yaml'),
         'v3':Path('configs/bench2dex/shadow_thumb_v3.yaml'),
         'repair':Path('configs/bench2dex/shadow_thumb_v3_geometry_repair.yaml')}


def pair_key(selection):return selection['dexonomy_object'],selection['category']


def prepare(output):
    output=Path(output)
    if output.exists():raise ValueError('Use fresh output or explicit resume')
    inventory=json.loads(INVENTORY.read_text());catalog={r['object']:r for r in inventory['objects']}
    grouped=defaultdict(list);extents=defaultdict(list);source_attempts=defaultdict(set);families={};parents=[]
    for root in PARENTS:
        plan=json.loads((root/'plan.json').read_text());verify_v3(plan)
        parents.append(file_receipt(root/'plan.json'))
        for asset in plan['assets']:families.setdefault(asset['dexonomy_object'],asset.get('family'))
        for job in plan['jobs']:
            folder=root/'samples'/job['case_id'];row=verify_completed(folder,v3_identity(plan,job))
            if row is None or row['status']=='error':raise ValueError('Missing existing source case')
            result=json.loads((folder/'result.json').read_text());selection=job['selection'];key=pair_key(selection)
            source_attempts[key].add((str(Path(selection['source']['path'])),selection['source_index']))
            scene=load_scene_cfg(selection['scene_path']);obj=scene['scene'][scene['task']['obj_name']]
            if selection['dexonomy_object'] not in extents:
                pass
            mesh=trimesh.load(obj['file_path'],force='mesh')
            size=mesh.extents*np.asarray(obj['scale'])*selection['scene_scale_multiplier']
            extents[selection['dexonomy_object']].append(size)
            if row['status']=='kinematic_candidate':
                score=max(v['mean_shape_error'] for v in result['selected_quality']['phases'].values())
                grouped[key].append((score,str(folder),file_receipt(folder/'result.json'),file_receipt(folder/'postures.npz')))
    models=sorted(extents);mesh_extents={};raw_cache={};scene_cache={};receipts={};resources={}
    def receipt(path):
        path=Path(path);key=str(path.resolve())
        if key not in receipts:receipts[key]=file_receipt(path)
        if receipts[key]['status']!='present':raise FileNotFoundError(path)
        return receipts[key]
    def raw(path):
        if str(path) not in raw_cache:
            data=np.load(path,allow_pickle=True).item() # trusted installed local sources
            n=len(data['grasp_qpos'])
            if not n or any(np.asarray(data[p+'_qpos']).shape!=(n,29) for p in ['pregrasp','grasp','squeeze']):raise ValueError('Invalid source '+str(path))
            raw_cache[str(path)]=data
        return raw_cache[str(path)]
    all_assets=[];assets=[];jobs=[];coverage=[]
    for mi,name in enumerate(models,1):
        reference=np.median(np.asarray(extents[name]),axis=0);info=catalog[name]
        mesh_extents[name]=trimesh.load(info['mesh'],force='mesh').extents
        asset={'bench_object':name,'dexonomy_object':name,'family':families.get(name),'tasks':[],
            'match_level':'native_dexonomy_model','entries':[],'requested_grasps':len(info['categories']),'source_shortfall':0}
        pending={**asset,'entries':[]}
        for category in sorted(info['categories'],key=lambda c:int(c.split('_')[0])):
            key=(name,category);cid=f'model{mi:03d}__{category}'
            entry={'case_id':cid,'category':category};asset['entries'].append(entry)
            if grouped[key]:
                score,folder,result_receipt,poses_receipt=min(grouped[key],key=lambda x:(x[0],x[1]))
                coverage.append({'case_id':cid,'object':name,'category':category,'kind':'reused',
                    'result_folder':folder,'result':result_receipt,'postures':poses_receipt})
                continue
            choices=[]
            source_root=Path('assets/object/Dexonomy_GRASP_shadow/succ_collect')/category/name/'floating'
            for path in sorted(source_root.glob('*.npy')):
                value=raw(path);scene_path=str(value['scene_path'])
                if scene_path not in scene_cache:scene_cache[scene_path]=load_scene_cfg(scene_path)
                obj=scene_cache[scene_path]['scene'][scene_cache[scene_path]['task']['obj_name']]
                base=mesh_extents[name]*np.asarray(obj['scale'])
                for index,scale in enumerate(value['scene_scale']):
                    size=base*float(scale);error=float(np.linalg.norm(np.log(np.sort(size)/np.sort(reference))))
                    poses=np.asarray([value[p+'_qpos'][index] for p in ['pregrasp','grasp','squeeze']])
                    if not np.isfinite(poses).all() or not np.allclose(np.linalg.norm(poses[:,3:7],axis=1),1,atol=1e-4):continue
                    choices.append((error,(str(path),index) in source_attempts[key],str(path),index,size))
            if not choices:raise ValueError('No valid representative for '+str(key))
            best=min(c[0] for c in choices)
            # Prefer a fresh source row for a rejected category, within 2% log-size error of best.
            choice=min((c for c in choices if c[0]<=best+.02),key=lambda c:(c[1],c[0],c[2],c[3]))
            error,previous,path,index,size=choice;value=raw(Path(path))
            selection={'id':cid,'bench_object':name,'category':category,'dexonomy_object':name,
                'match_level':'native_dexonomy_model','status':'source_extracted_not_transferred',
                'source':receipt(path),'source_index':int(index),'source_count_in_file':len(value['grasp_qpos']),
                'scene_path':str(value['scene_path']),'scene_scale_multiplier':float(value['scene_scale'][index]),
                'size_selection':{'method':'nearest_existing_scale_to_median_current_model_extent',
                    'target_size_known':False,'reference_extents_m':reference.tolist(),'source_extents_m':size.tolist(),
                    'extent_log_error':error,'previously_attempted_source_row':bool(previous)},
                'geometry_identity_verified':False,'physical_transfer_verified':False}
            job={'case_id':cid,'selection':selection,'aliases':[{'bench_object':name,'category':category,'match_level':'native_dexonomy_model'}]}
            jobs.append(job);pending['entries'].append(entry)
            coverage.append({'case_id':cid,'object':name,'category':category,'kind':'new'})
            scene=scene_cache[str(value['scene_path'])];obj=scene['scene'][scene['task']['obj_name']]
            for item in [receipt(value['scene_path']),receipt(obj['file_path']),*model_resources(obj['xml_path'])]:resources[item['path']]=item
        all_assets.append(asset)
        if pending['entries']:assets.append(pending)
    for item in [*model_resources('assets/hand/shadow/right.xml'),*model_resources(TARGET),receipt(TARGET.parent/'model_report.json')]:resources[item['path']]=item
    coverage_plan={'scope':'all_available_grasp_types_for_current_44_source_models','models':models,'assets':all_assets,
        'entries':coverage,'total_types':len(coverage),'reused_types':sum(e['kind']=='reused' for e in coverage),
        'new_types':len(jobs),'source_records_not_exhausted':True,'parents':parents,'inventory':file_receipt(INVENTORY),
        'physical_passed':None,'full_task_passed':None}
    coverage_plan['identity']=digest(coverage_plan)
    output.mkdir(parents=True);atomic_json(output/'coverage_plan.json',coverage_plan)
    plan={'schema_version':1,'scope':'missing_or_rejected_grasp_categories_on_current_models',
        'inputs':{'matches':file_receipt(output/'coverage_plan.json'),'profile':file_receipt(output/'coverage_plan.json'),
            'grasp_config':file_receipt(CONFIGS['v1']),'engine':file_receipt(Path(__file__).with_name('shadow_retarget.py')),
            'batch_engine':file_receipt(Path(__file__).with_name('shadow_batch.py')),'target_model':receipt(TARGET)},
        'resources':list(resources.values()),'assets':assets,'jobs':jobs,'deferred_assets':[],
        'asset_count':len(assets),'coverage_entries':len(jobs),'unique_source_cases':len(jobs),'side':'right','physical_passed':None}
    plan['plan_identity']=digest(plan);(output/'v1').mkdir();atomic_json(output/'v1/plan.json',plan)
    return coverage_plan


def run_stage(stage,folder,workers,progress_root):
    folder=Path(folder);plan=json.loads((folder/'plan.json').read_text());started=monotonic()
    if stage=='v1':verify_plan(plan);identity=job_identity;summary=summarize
    elif stage=='v2':verify_v2(plan);identity=v2_identity;summary=v2_summary
    else:verify_v3(plan);identity=v3_identity;summary=v3_summary
    rows={};pending=[]
    for job in plan['jobs']:
        dest=folder/'samples'/job['case_id'];expected=identity(plan,job);done=verify_completed(dest,expected)
        if done:rows[job['case_id']]=done
        elif dest.exists():raise ValueError('Incomplete case requires inspection: '+str(dest))
        else:pending.append((job,str(dest),expected))
    def save():
        result=summary(plan,rows);atomic_json(folder/'summary.json',result)
        atomic_json(Path(progress_root)/'progress.json',{'stage':stage,'completed':len(rows),'total':len(plan['jobs']),
            'status_counts':result['status_counts'],'elapsed_s_this_session':monotonic()-started,'finished':False})
        return result
    save()
    # This new all-category runner uses a bounded pool; frozen legacy engines remain unchanged.
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        futures=[]
        for job,dest,expected in pending:
            if stage=='v1':f=ex.submit(_run_job,job,plan['inputs']['target_model']['path'],plan['inputs']['grasp_config']['path'],dest,expected)
            elif stage=='v2':f=ex.submit(run_v2_case,job,plan['inputs']['config']['path'],dest,expected)
            else:f=ex.submit(run_v3_case,job,plan['inputs']['config']['path'],dest,expected)
            futures.append(f)
        for f in as_completed(futures):
            row=f.result();rows[row['case_id']]=row;save()
            if len(rows)%10==0 or row['status']=='error':print(json.dumps({'stage':stage,'completed':len(rows),'total':len(plan['jobs']),'status':row['status']}),flush=True)
    result=save()
    if result['status_counts'].get('error'):raise RuntimeError('Stage contains execution errors; inspect before continuing')
    return result


def run(output,workers=8):
    output=Path(output)
    if not 1<=workers<=8:raise ValueError('Use one to eight workers')
    run_stage('v1',output/'v1',workers,output)
    if not (output/'v2/plan.json').is_file():prepare_v2(output/'v1',CONFIGS['v2'],output/'v2')
    run_stage('v2',output/'v2',workers,output)
    if not (output/'v3/plan.json').is_file():prepare_v3(output/'v2',CONFIGS['v3'],output/'v3')
    run_stage('v3',output/'v3',workers,output)
    from tools.finalize_shadow_thumb_v3 import prepare_repair,publish
    if not (output/'geometry_repair/plan.json').is_file():prepare_repair(output/'v3',CONFIGS['repair'],output/'geometry_repair')
    run_stage('repair',output/'geometry_repair',workers,output)
    if not (output/'final/plan.json').is_file():publish(output/'v3',output/'geometry_repair',output/'final')
    atomic_json(output/'progress.json',{'stage':'optimization_complete','finished':True,
        'note':'Static optimization only; review, contact audit and dynamics reported separately'})
