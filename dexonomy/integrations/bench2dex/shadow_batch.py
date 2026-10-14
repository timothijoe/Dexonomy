"""Fixed multi-grasp asset coverage, deduplicated optimization and verified resume."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import trimesh
import yaml

from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json, file_receipt, sha256
from .shadow_retarget import transfer


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def ordered_categories(available,preferred,fallback,count):
    ordered=list(dict.fromkeys([*preferred,*fallback]))
    return [name for name in ordered if name in available][:count]


def case_key(selection):
    return selection['source']['sha256'],selection['source_index'],selection['category']


def model_resources(path):
    """Include collision meshes as well as XML in the resume identity."""
    path=Path(path).resolve();paths={path}
    root=ET.parse(path).getroot();compiler=root.find('compiler')
    meshdir=compiler.get('meshdir','.') if compiler is not None else '.'
    for mesh in root.iter('mesh'):
        if mesh.get('file'):paths.add((path.parent/meshdir/mesh.get('file')).resolve())
    for include in root.iter('include'):
        paths.update(Path(item['path']) for item in model_resources(path.parent/include.get('file')))
    receipts=[file_receipt(p) for p in sorted(paths)]
    if any(item['status']!='present' for item in receipts):raise FileNotFoundError('Model dependency missing')
    return receipts


def prepare_plan(matches_path,profile_path,object_root,target_model,grasp_config,output):
    output=Path(output)
    if output.exists():raise ValueError('Batch output exists; use --resume or a new directory')
    matches=json.loads(Path(matches_path).read_text())
    profile=yaml.safe_load(Path(profile_path).read_text())
    if profile.get('schema_version')!=1 or not 3<=profile['grasps_per_asset']<=4:
        raise ValueError('Batch profile must request three or four grasps per asset')
    if profile['source_side']!='right' or profile['target_side']!='right':
        raise ValueError('This batch uses verified right-hand models')
    conversion_path=Path(target_model).parent/'model_report.json'
    conversion=json.loads(conversion_path.read_text())
    if not conversion['urdf_mujoco_fk_passed'] or conversion['mjcf']['sha256']!=sha256(target_model):
        raise ValueError('Target must match the verified original Wuji v1 conversion')
    output.mkdir(parents=True)
    raw_cache,scene_cache,receipts_cache,geometry_cache={},{},{},{}
    object_root=Path(object_root)
    frozen={(s['bench_object'],s['category']):s for s in matches['initial_selection'] if s['status']=='source_extracted_not_transferred'}
    target_sizes={s['bench_object']:s['size_selection']['bench_extents_m'] for s in matches['initial_selection'] if s.get('size_selection',{}).get('target_size_known')}
    def raw(path):
        key=str(path)
        if key not in raw_cache:
            value=np.load(path,allow_pickle=True).item()  # fixed trusted local dataset
            size=len(np.asarray(value['grasp_qpos']))
            if size<1 or any(np.asarray(value[p+'_qpos']).shape!=(size,29) for p in ['pregrasp','grasp','squeeze']):
                raise ValueError(f'Invalid source three-phase state: {path}')
            raw_cache[key]=value
        return raw_cache[key]
    def receipt(path):
        key=str(Path(path).resolve())
        if key not in receipts_cache:receipts_cache[key]=file_receipt(Path(path))
        return receipts_cache[key]
    def choose_source(row,candidate,category):
        original=frozen.get((row['bench_object'],category))
        folder=object_root/'Dexonomy_GRASP_shadow/succ_collect'/category/candidate['dexonomy_object']/'floating'
        paths=sorted(folder.glob('*.npy'))
        if not paths:raise FileNotFoundError(f'No declared source files in {folder}')
        if original and original['dexonomy_object']==candidate['dexonomy_object']:
            path,index=Path(original['source']['path']),original['source_index']
            size_selection=original.get('size_selection',{})
        elif row['bench_object'] in target_sizes:
            target=np.sort(target_sizes[row['bench_object']])
            if candidate['dexonomy_object'] not in geometry_cache:
                geometry_cache[candidate['dexonomy_object']]=trimesh.load(candidate['mesh']['path'],force='mesh').extents
            extents=geometry_cache[candidate['dexonomy_object']];choices=[]
            for path in paths:
                value=raw(path)
                scene_name=str(value['scene_path'])
                if scene_name not in scene_cache:scene_cache[scene_name]=load_scene_cfg(scene_name)
                scene=scene_cache[scene_name]
                base=np.asarray(scene['scene'][scene['task']['obj_name']]['scale'])
                for index,multiplier in enumerate(value['scene_scale']):
                    current=extents*base*float(multiplier)
                    error=float(np.linalg.norm(np.log(np.sort(current)/target)))
                    choices.append((error,str(path),index,current))
            error,path,index,current=min(choices,key=lambda x:x[:3]);path=Path(path)
            size_selection={'method':'nearest_existing_source_AABB','target_size_known':True,
                            'bench_extents_m':target.tolist(),'source_extents_m':current.tolist(),'extent_log_error':error}
        else:
            path,index=paths[0],profile['selection_index_if_target_size_unknown']
            size_selection={'method':'fixed_first_source','target_size_known':False}
        value=raw(path)
        poses=[np.asarray(value[p+'_qpos'])[index] for p in ['pregrasp','grasp','squeeze']]
        if not all(np.isfinite(q).all() and abs(np.linalg.norm(q[3:7])-1)<1e-4 for q in poses):
            raise ValueError(f'Invalid source pose: {path}, {index}')
        return {'id':row['bench_object']+'__'+category,'bench_object':row['bench_object'],'category':category,
                'status':'source_extracted_not_transferred','dexonomy_object':candidate['dexonomy_object'],
                'match_level':candidate['match_level'],'source':receipt(path),'source_index':int(index),
                'source_count_in_file':len(value['grasp_qpos']),'scene_path':str(value['scene_path']),
                'scene_scale_multiplier':float(value['scene_scale'][index]),'size_selection':size_selection,
                'geometry_identity_verified':False,'physical_transfer_verified':False}
    assets=[];jobs=[];keys={};skipped=[]
    for row in matches['object_matches']:
        if not row['candidates']:
            skipped.append({'bench_object':row['bench_object'],'reason':'no_local_candidate_deferred_by_user'});continue
        candidate=row['candidates'][0]
        preferred=profile.get('asset_category_overrides',{}).get(row['bench_object'],profile['family_categories'].get(row['family'],[]))
        selected=ordered_categories(candidate['shadow_categories'],preferred,profile['fallback_categories'],profile['grasps_per_asset'])
        asset={'bench_object':row['bench_object'],'family':row['family'],'tasks':row['tasks'],
               'match_level':candidate['match_level'],'dexonomy_object':candidate['dexonomy_object'],
               'entries':[],'requested_grasps':profile['grasps_per_asset'],
               'source_shortfall':max(0,profile['minimum_grasps_per_asset']-len(selected))}
        for category in selected:
            selection=choose_source(row,candidate,category);key=case_key(selection)
            alias={'bench_object':row['bench_object'],'category':category,'match_level':candidate['match_level']}
            if key not in keys:
                case_id=f'case_{len(jobs)+1:04d}__{category}'
                selection['id']=case_id
                job={'case_id':case_id,'selection':selection,'aliases':[alias]}
                keys[key]=job;jobs.append(job)
            else:job=keys[key];job['aliases'].append(alias)
            asset['entries'].append({'case_id':job['case_id'],'category':category})
        assets.append(asset)
    shared=[*model_resources('assets/hand/shadow/right.xml'),*model_resources(target_model),receipt(conversion_path)]
    object_resources=[];seen_scenes=set()
    for job in jobs:
        scene_path=job['selection']['scene_path']
        if scene_path in seen_scenes:continue
        seen_scenes.add(scene_path);scene=load_scene_cfg(scene_path);obj=scene['scene'][scene['task']['obj_name']]
        object_resources += [receipt(scene_path),receipt(obj['file_path']),*model_resources(obj['xml_path'])]
    resources={item['path']:item for item in [*shared,*object_resources]}
    inputs={'matches':file_receipt(Path(matches_path)),'profile':file_receipt(Path(profile_path)),
            'grasp_config':file_receipt(Path(grasp_config)),'engine':file_receipt(Path(__file__).parent/'shadow_retarget.py'),
            'batch_engine':file_receipt(Path(__file__)),'target_model':file_receipt(Path(target_model))}
    plan={'schema_version':1,'scope':'all_currently_matched_assets_static_shadow_to_wuji_v1_right',
          'inputs':inputs,'resources':list(resources.values()),'assets':assets,'jobs':jobs,'deferred_assets':skipped,
          'asset_count':len(assets),'coverage_entries':sum(len(a['entries']) for a in assets),
          'unique_source_cases':len(jobs),'side':'right','physical_passed':None}
    plan['plan_identity']=digest(plan)
    atomic_json(output/'plan.json',plan)
    return plan


def verify_plan(plan):
    original=plan['plan_identity'];copy=dict(plan);copy.pop('plan_identity')
    if digest(copy)!=original:raise ValueError('Batch plan changed')
    items=[*plan['inputs'].values(),*plan['resources'],*[j['selection']['source'] for j in plan['jobs']]]
    for item in items:
        if not Path(item['path']).is_file() or sha256(item['path'])!=item['sha256']:
            raise ValueError('Batch source/config/model identity changed: '+item['path'])


def job_identity(plan,job):
    return digest({'plan_identity':plan['plan_identity'],'job':job})


def verify_completed(folder,expected):
    path=folder/'receipt.json'
    if not path.is_file():return None
    receipt=json.loads(path.read_text())
    if receipt['identity']!=expected:raise ValueError('Completed case belongs to a different plan')
    for item in receipt['artifacts']:
        target=(folder/item['path']).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file() or sha256(target)!=item['sha256']:
            raise ValueError('Completed artifact changed: '+str(target))
    return receipt['row']


def _run_job(job,target_model,config_path,folder,identity):
    folder=Path(folder)
    try:
        result=transfer(job['selection'],Path(target_model),Path(config_path),folder,render=True)
        result['bench_targets']=sorted({a['bench_object'] for a in job['aliases']})
        result['batch_aliases']=job['aliases'];atomic_json(folder/'result.json',result)
        row={'case_id':job['case_id'],'status':result['status'],'failure_reasons':result['failure_reasons'],
             'solver_termination':result['solver']['termination'],'seconds':result['seconds'],
             'render_error':result.get('render_error'),'postures_available':True}
    except Exception as exc:
        folder.mkdir(parents=True,exist_ok=True)
        row={'case_id':job['case_id'],'status':'error','error':f'{type(exc).__name__}: {exc}',
             'postures_available':(folder/'postures.npz').is_file()}
        atomic_json(folder/'failure.json',row)
    artifacts=[]
    for path in sorted(folder.rglob('*')):
        if path.is_file():artifacts.append({'path':str(path.relative_to(folder)),'sha256':sha256(path)})
    atomic_json(folder/'receipt.json',{'schema_version':1,'identity':identity,'row':row,'artifacts':artifacts})
    return row


def summarize(plan,rows):
    ordered=[rows[j['case_id']] for j in plan['jobs'] if j['case_id'] in rows]
    return {'schema_version':1,'plan_identity':plan['plan_identity'],'asset_count':plan['asset_count'],
            'coverage_entries':plan['coverage_entries'],'unique_source_cases':plan['unique_source_cases'],
            'completed_source_cases':len(ordered),'status_counts':dict(Counter(r['status'] for r in ordered)),
            'all_cases_terminal':len(ordered)==len(plan['jobs']),
            'cases_with_postures':sum(bool(r['postures_available']) for r in ordered),'results':ordered,
            'physical_passed':None,'full_task_passed':None}


def run_batch(plan,output,workers=3):
    if not 1<=workers<=4:raise ValueError('Use one to four bounded CPU workers')
    output=Path(output);verify_plan(plan)
    rows={};pending=[]
    for job in plan['jobs']:
        folder=output/'samples'/job['case_id'];identity=job_identity(plan,job)
        completed=verify_completed(folder,identity)
        if completed:rows[job['case_id']]=completed
        elif folder.exists():raise ValueError('Incomplete case directory cannot be silently reused: '+str(folder))
        else:pending.append((job,folder,identity))
    atomic_json(output/'summary.json',summarize(plan,rows))
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as executor:
        futures={executor.submit(_run_job,job,plan['inputs']['target_model']['path'],plan['inputs']['grasp_config']['path'],str(folder),identity):job for job,folder,identity in pending}
        for future in as_completed(futures):
            row=future.result();rows[row['case_id']]=row
            atomic_json(output/'summary.json',summarize(plan,rows))
            print(json.dumps({'completed':len(rows),'total':len(plan['jobs']),**row},ensure_ascii=False),flush=True)
    return summarize(plan,rows)
