#!/usr/bin/env python3
"""Count installed source grasp records for the actually mapped native meshes."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt


def count(output):
    output=Path(output)
    if output.exists():raise ValueError('Use a fresh statistics output')
    base_path=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/plan.json')
    extra_path=Path('output/shadow_wuji_v4/expansion_pilot_2026-10-15/final/plan.json')
    inv_path=Path('output/shadow_wuji_v4/expansion_inventory_2026-10-15/inventory.json')
    matches_path=Path('output/shadow_wuji_v1/asset_selection_v3/matches.json')
    base,extra,inv,matches=[json.loads(p.read_text()) for p in [base_path,extra_path,inv_path,matches_path]]
    original={j['selection']['dexonomy_object'] for j in base['jobs']}
    additional={j['selection']['dexonomy_object'] for j in extra['jobs']}
    models=original|additional;catalog={o['object']:o for o in inv['objects']}
    plans=[base,extra];extra_inputs=[]
    all_types=Path('output/shadow_wuji_all_types/current44_2026-10-16')
    if (all_types/'final/summary.json').is_file() and json.loads((all_types/'final/summary.json').read_text())['all_cases_terminal']:
        plans.append(json.loads((all_types/'final/plan.json').read_text()));extra_inputs.append(all_types/'final/plan.json')
    selected={(j['selection']['dexonomy_object'],j['selection']['category'],j['selection']['source']['sha256'],j['selection']['source_index']) for plan in plans for j in plan['jobs']}
    chosen=Counter(key[0] for key in selected)
    alias_pairs={(a['bench_object'],a['category']) for plan in plans for j in plan['jobs'] for a in j['aliases']}
    root=Path('assets/object/Dexonomy_GRASP_shadow/succ_collect');rows=[];sources=[];categories=set()
    for name in sorted(models):
        counts=Counter();available=[]
        for category in catalog[name]['categories']:
            paths=sorted((root/category/name/'floating').glob('*.npy'))
            if not paths:raise ValueError('Previously indexed source category is missing')
            for path in paths:
                raw=np.load(path,allow_pickle=True).item() # trusted installed local Dexonomy data
                n=len(np.asarray(raw['grasp_qpos']))
                if n<1 or any(np.asarray(raw[p+'_qpos']).shape!=(n,29) for p in ['pregrasp','grasp','squeeze']):
                    raise ValueError('Invalid three-phase source dimensions: '+str(path))
                if np.asarray(raw['scene_scale']).shape!=(n,):raise ValueError('Scale count mismatch: '+str(path))
                counts[category]+=n;sources.append({'path':str(path),'grasp_records':n})
            available.append(category);categories.add(category)
        row={'object':name,'group':'previous' if name in original else 'new_pilot',
            'categories':len(available),'source_files':sum(1 for r in sources if '/'+name+'/' in r['path']),
            'source_grasp_records':sum(counts.values()),'mapped_source_cases':chosen[name],
            'records_by_category':dict(counts)}
        rows.append(row);print(json.dumps({'objects_counted':len(rows),'objects':len(models),'grasp_records':row['source_grasp_records']}),flush=True)
    total=sum(r['source_grasp_records'] for r in rows)
    total_cases=len(selected)
    report={'date':'2026-10-16','installed_meshes_with_shadow':inv['objects_with_shadow'],
        'previous_mapped_source_models':len(original),'new_pilot_source_models':len(additional-original),
        'mapped_source_models':len(models),'mapped_model_fraction':len(models)/inv['objects_with_shadow'],
        'bench_matched_targets':base['asset_count'],'bench_task_targets':matches['bench_object_count'],
        'bench_target_fraction':base['asset_count']/matches['bench_object_count'],
        'mapped_unique_source_cases':total_cases,'mapped_target_coverage_entries':len(alias_pairs),
        'all_type_coverage_included':bool(extra_inputs),
        'unique_taxonomy_categories':len(categories),'object_category_pairs':sum(r['categories'] for r in rows),
        'minimum_categories_per_model':min(r['categories'] for r in rows),'maximum_categories_per_model':max(r['categories'] for r in rows),
        'source_files_read':len(sources),'source_grasp_records':total,'source_phase_postures':3*total,
        'mapped_case_fraction_of_available_records':total_cases/total,
        'groups':{group:{'models':sum(r['group']==group for r in rows),
            'object_category_pairs':sum(r['categories'] for r in rows if r['group']==group),
            'source_grasp_records':sum(r['source_grasp_records'] for r in rows if r['group']==group)} for group in ['previous','new_pilot']},
        'models':rows,'sources':sources,'inputs':[file_receipt(p) for p in [base_path,extra_path,inv_path,matches_path,*extra_inputs]],
        'limitations':['Counts are for installed local floating Shadow sources, not the entire upstream Dexonomy distribution',
            'One grasp record includes pregrasp/grasp/squeeze; these phases are not three separate grasps',
            'Different scales and source rows counted separately; not deduplicated by geometric similarity',
            'Source availability and mapped static cases do not establish physical success',
            'Bench2Dex target aliases and native source meshes use different denominators']}
    output.mkdir(parents=True);atomic_json(output/'summary.json',report)
    with (output/'models.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['object','group','categories','source_files','source_grasp_records','mapped_source_cases'])
        writer.writeheader();writer.writerows({k:r[k] for k in writer.fieldnames} for r in rows)
    md=['# 当前映射物体的 Shadow 来源数量','',
        f"不同来源模型：{len(models)}/{inv['objects_with_shadow']}（{len(models)/inv['objects_with_shadow']:.4%}）。",'',
        f"完整抓取记录 {total:,}；三阶段姿态 {3*total:,}；物体/握法类别组合 {sum(r['categories'] for r in rows)}；全局握法类别 {len(categories)}。",'',
        f"实际迁移来源 {total_cases} 条；目标覆盖条目 {len(alias_pairs)}；Bench2Dex 目标覆盖 {base['asset_count']}/{matches['bench_object_count']}。",'',
        '以上均为本地来源和当前试验统计，不是物理成功率。不同尺度记录分别计数。','',
        '| 模型 | 握法类别 | 完整抓取记录 | 已迁移来源 |','| --- | ---: | ---: | ---: |']
    for r in rows:md.append(f"| {r['object']} | {r['categories']} | {r['source_grasp_records']} | {r['mapped_source_cases']} |")
    (output/'summary.md').write_text('\n'.join(md)+'\n')
    return {k:v for k,v in report.items() if k not in ['models','sources','inputs','limitations']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v4/coverage_counts_2026-10-16'))
    a=p.parse_args();print(json.dumps(count(a.output),ensure_ascii=False,indent=2),flush=True)
