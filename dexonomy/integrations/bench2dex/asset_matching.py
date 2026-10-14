"""Bounded, auditable semantic matching and Shadow-source extraction.

Shared names are identity candidates, never proof of geometric equivalence.
Only explicitly supplied, trusted local Dexonomy NPY files are deserialized.
"""
from collections import Counter
import json
from pathlib import Path
import re

import numpy as np
import yaml

from .common import atomic_json, file_receipt, sha256


def normalized_name(value):
    return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')


def same_ycb_name(bench, dex):
    return dex.startswith('ddg_ycb_') and normalized_name(bench) == normalized_name(dex[len('ddg_ycb_'):])


def object_tokens(name):
    # Explicit ShapeNet class labels avoid matching products such as a hair
    # straightener with "plates" in its title to a dinner plate.
    match = re.match(r'^(?:core|sem)_([^_]+)_', name, re.I)
    if match:
        return {normalized_name(match[1])}
    return set(normalized_name(name).split('_'))


def build_matching(catalog_path, object_root, config_path, output):
    catalog_path, object_root, config_path, output = map(Path,(catalog_path,object_root,config_path,output))
    if output.exists():
        raise ValueError('Matching output already exists; use a new directory')
    cfg = yaml.safe_load(config_path.read_text())
    if cfg.get('schema_version') != 1:
        raise ValueError('Unsupported matching configuration')
    catalog = json.loads(catalog_path.read_text())
    pool = {}
    for dataset in ['DGN_5k','objaverse_5k']:
        root = object_root/dataset/'processed_data'
        split = object_root/dataset/'valid_split/all.json'
        if not root.is_dir(): continue
        names = json.loads(split.read_text()) if split.is_file() else sorted(p.name for p in root.iterdir() if p.is_dir())
        for name in names:
            if (root/name).is_dir(): pool[name] = {'dataset':dataset,'path':root/name,'tokens':object_tokens(name)}
    shadow_root = object_root/'Dexonomy_GRASP_shadow/succ_collect'
    categories = sorted(p.name for p in shadow_root.iterdir() if p.is_dir())
    available_cache = {}
    def available(name):
        if name not in available_cache:
            available_cache[name] = {cat:sorted((shadow_root/cat/name/'floating').glob('*.npy'))
                                     for cat in categories if (shadow_root/cat/name/'floating').is_dir()}
            available_cache[name] = {k:v for k,v in available_cache[name].items() if v}
        return available_cache[name]
    rows = []
    for bench, entries in sorted(catalog['object_directories'].items()):
        bench_id = re.match(r'\d+',bench).group()
        family = next((name for name,spec in cfg['families'].items() if bench_id in spec['bench_ids']),None)
        family_cfg = cfg['families'].get(family,{})
        exact = sorted(name for name in pool if same_ycb_name(bench,name))
        candidates = [(name,'same_ycb_id_and_name') for name in exact]
        if family:
            tokens = set(family_cfg['tokens'])
            others = [name for name,info in pool.items() if name not in exact and tokens & info['tokens']]
            preferred = family_cfg.get('preferred_sources',[])
            bench_words = set(normalized_name(re.sub(r'^\d+[_-]','',bench)).split('_'))
            specific_words = bench_words - tokens
            others.sort(key=lambda n:(-len(specific_words & pool[n]['tokens']),0 if n in preferred else 1,
                                      preferred.index(n) if n in preferred else 0,
                                      -len(bench_words & pool[n]['tokens']),n))
            candidates += [(name,'same_named_category' if bench_words & pool[name]['tokens'] else 'similar_geometry_family') for name in others]
        chosen = []
        for name,level in candidates:
            files = available(name)
            if not files and level != 'same_ycb_id_and_name': continue
            preferred_categories = family_cfg.get('grasp_categories',[])
            ordered = [cat for cat in preferred_categories if cat in files] + [cat for cat in files if cat not in preferred_categories]
            chosen.append({'dexonomy_object':name,'dataset':pool[name]['dataset'],
                           'match_level':level,'geometry_identity_verified':False,
                           'mesh':file_receipt(pool[name]['path']/'mesh/simplified.obj'),
                           'shadow_categories':ordered,
                           'shadow_file_count':sum(len(v) for v in files.values()),
                           'example_sources':{cat:str(files[cat][0]) for cat in ordered[:3]}})
            if len(chosen) >= cfg['max_candidates_per_asset']: break
        rows.append({'bench_object':bench,'family':family,'tasks':sorted({e['task'] for e in entries}),
                     'bench_asset_paths':sorted({e['asset_path'] for e in entries}),
                     'bench_geometry_available':any(e['source']['status']=='present' for e in entries),
                     'body_types':sorted({e['body_type'] for e in entries}),
                     'match_status':chosen[0]['match_level'] if chosen else 'no_local_candidate',
                     'candidates':chosen,'physical_transfer_verified':False})
    selected = []
    output.mkdir(parents=True,exist_ok=True)
    for desired in cfg['initial_selection']:
        row = next(r for r in rows if r['bench_object']==desired['bench_object'])
        cat = desired['category']
        candidate = next((c for c in row['candidates'] if cat in available(c['dexonomy_object'])),None)
        if candidate is None:
            selected.append({**desired,'status':'missing_shadow_source'});continue
        paths = available(candidate['dexonomy_object'])[cat]
        path = paths[0]
        index = 0
        bench_geometry = None
        size_selection = {'method':'first_declared_source_index','target_size_known':False}
        present = next((e for e in catalog['object_directories'][desired['bench_object']] if Path(e['source']['path']).is_file()),None)
        if present and cfg.get('source_pose_selection')=='nearest_available_target_dimensions':
            import trimesh
            from .local_grasp import usd_object_mesh
            bench_geometry = usd_object_mesh(Path(present['source']['path']),present['scale_xyz'],output/(desired['bench_object']+'_bench.obj'))
            target_extents = np.ptp(np.asarray(bench_geometry['bounds_object_m']),axis=0)
            source_extents = trimesh.load(candidate['mesh']['path'],force='mesh').extents
            scores = []
            for possible in paths:
                data = np.load(possible,allow_pickle=True).item()  # trusted installed data
                scene = np.load(data['scene_path'],allow_pickle=True).item()
                base = np.asarray(scene['scene'][scene['task']['obj_name']]['scale'],dtype=float)
                for j,multiplier in enumerate(np.asarray(data['scene_scale'])):
                    extents = source_extents*base*float(multiplier)
                    error = float(np.linalg.norm(np.log(np.sort(extents)/np.sort(target_extents))))
                    scores.append((error,str(possible),j,extents))
            error,chosen_path,index,extents = min(scores,key=lambda item:item[:3])
            path = Path(chosen_path)
            size_selection = {'method':'nearest_sorted_AABB_extents_log_ratio','target_size_known':True,
                              'extent_log_error':error,'bench_extents_m':target_extents.tolist(),
                              'source_extents_m':extents.tolist(),
                              'note':'Selects an existing source pose and scale; does not rescale source grasp or certify mesh identity'}
        raw = np.load(path,allow_pickle=True).item()  # trusted installed source data
        count = len(np.asarray(raw['grasp_qpos']))
        if count < 1 or any(np.asarray(raw[f'{phase}_qpos']).shape != (count,29) for phase in ['pregrasp','grasp','squeeze']):
            raise ValueError(f'Invalid Shadow phase dimensions: {path}')
        poses = {phase:np.asarray(raw[f'{phase}_qpos'])[index].astype(float) for phase in ['pregrasp','grasp','squeeze']}
        if not all(np.isfinite(q).all() and abs(np.linalg.norm(q[3:7])-1)<1e-4 for q in poses.values()):
            raise ValueError(f'Invalid Shadow source pose: {path}')
        source_id = f'{desired["bench_object"]}__{cat}'
        np.savez_compressed(output/f'{source_id}.npz',**{f'{p}_qpos':q for p,q in poses.items()})
        selected.append({**desired,'id':source_id,'status':'source_extracted_not_transferred',
                         'dexonomy_object':candidate['dexonomy_object'],'match_level':candidate['match_level'],
                         'source':file_receipt(path),'source_index':index,'source_count_in_file':count,
                         'scene_path':str(raw['scene_path']),'scene_scale_multiplier':float(np.asarray(raw['scene_scale'])[index]),
                         'size_selection':size_selection,'bench_geometry':bench_geometry,
                         'extracted_poses':file_receipt(output/f'{source_id}.npz'),
                         'geometry_identity_verified':False,'physical_transfer_verified':False})
    report = {'schema_version':1,'inputs':{'catalog':file_receipt(catalog_path),'matching_config':file_receipt(config_path)},
              'bench_object_count':len(rows),'locally_indexed_dexonomy_objects':len(pool),
              'match_counts':dict(Counter(r['match_status'] for r in rows)),
              'object_matches':rows,'initial_selection':selected,
              'limitations':['Names and families are candidates; no exact geometric identity asserted',
                             'Only locally installed valid DGN objects and installed Objaverse meshes indexed',
                             'NPZ phases are source extraction, not generated Wuji poses',
                             'Family compatibility and task grasp regions require review']}
    atomic_json(output/'matches.json',report)
    lines=['# Bench2Dex 与 Dexonomy 本地资产匹配','',f'任务资产目录：{len(rows)}；本地候选对象：{len(pool)}。','',
           '同 YCB 编号/名称仅为身份线索，未确认网格等价；类别候选未代表物理迁移通过。','',
           '| Bench2Dex 资产 | 匹配层级 | 首选 Dexonomy 对象 | Shadow 类别数 |','| --- | --- | --- | --- |']
    for row in rows:
        c=row['candidates'][0] if row['candidates'] else None
        lines.append(f'| {row["bench_object"]} | {row["match_status"]} | {c["dexonomy_object"] if c else "—"} | {len(c["shadow_categories"]) if c else 0} |')
    lines += ['','## 首批提取','', '| Bench2Dex 目标 | 来源对象 | 抓取类别 | 匹配 |','| --- | --- | --- | --- |']
    for s in selected:
        lines.append(f'| {s["bench_object"]} | {s.get("dexonomy_object","—")} | {s["category"]} | {s.get("match_level",s["status"])} |')
    (output/'matches.md').write_text('\n'.join(lines)+'\n')
    return report
