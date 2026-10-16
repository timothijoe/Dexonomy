#!/usr/bin/env python3
"""Inventory installed Shadow sources and prepare a small independent mapping pilot."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.asset_matching import object_tokens
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt

FAMILIES={'can':['1_Large_Diameter','3_Medium_Wrap','2_Small_Diameter'],
          'bottle':['1_Large_Diameter','3_Medium_Wrap','14_Tripod'],
          'box':['6_Prismatic_4_Finger','7_Prismatic_3_Finger','9_Palmar_Pinch']}


def inventory(object_root,batch,output):
    object_root,batch,output=map(Path,(object_root,batch,output))
    if output.exists():raise ValueError('Use a fresh inventory output')
    base=json.loads((batch/'plan.json').read_text())
    used={j['selection']['dexonomy_object'] for j in base['jobs']}
    meshes={}
    for dataset in ['DGN_5k','objaverse_5k']:
        root=object_root/dataset/'processed_data';split=object_root/dataset/'valid_split/all.json'
        names=json.loads(split.read_text()) if split.is_file() else sorted(p.name for p in root.iterdir() if p.is_dir())
        for name in names:
            mesh=root/name/'mesh/simplified.obj'
            if mesh.is_file():meshes[name]={'dataset':dataset,'mesh':str(mesh),'categories':[]}
    shadow=object_root/'Dexonomy_GRASP_shadow/succ_collect'
    cats=sorted(p for p in shadow.iterdir() if p.is_dir());directory_count=0
    for cat in cats:
        for obj in cat.iterdir():
            if obj.name not in meshes:continue
            floating=obj/'floating'
            if floating.is_dir() and next(floating.glob('*.npy'),None) is not None:
                meshes[obj.name]['categories'].append(cat.name);directory_count+=1
        print(json.dumps({'category':cat.name,'validated_category_directories':directory_count}),flush=True)
    objects=[{'object':name,**info,'already_mapped':name in used} for name,info in sorted(meshes.items())]
    ready=[o for o in objects if o['categories']];new=[o for o in ready if not o['already_mapped']]
    pilot=[]
    for family,categories in FAMILIES.items():
        candidates=[o for o in new if family in object_tokens(o['object']) and set(categories)<=set(o['categories'])]
        if not candidates:continue
        chosen=candidates[0];sources={}
        for category in categories:
            sources[category]=str(sorted((shadow/category/chosen['object']/'floating').glob('*.npy'))[0])
        pilot.append({**chosen,'family':family,'selected_categories':categories,'example_sources':sources})
    report={'mesh_objects':len(objects),'objects_with_shadow':len(ready),
            'already_mapped_source_meshes':len(used),'new_objects_with_shadow':len(new),
            'new_objects_with_at_least_three_categories':sum(len(o['categories'])>=3 for o in new),
            'shadow_categories':len(cats),'validated_category_directories':directory_count,
            'datasets':dict(Counter(o['dataset'] for o in ready)),
            'objects':objects,'pilot':pilot,'baseline':file_receipt(batch/'plan.json'),
            'limitations':['Source availability is not a transfer or physics pass',
                'Only installed meshes and nonempty floating Shadow categories indexed',
                'Scene and per-pose validity checked later during plan construction',
                'New Dexonomy models do not automatically close Bench2Dex geometry gaps']}
    output.mkdir(parents=True);atomic_json(output/'inventory.json',report)
    rows=[]
    for p in pilot:
        rows.append({'bench_object':p['object'],'family':p['family'],'tasks':[],
            'candidates':[{'dexonomy_object':p['object'],'dataset':p['dataset'],
                'match_level':'native_dexonomy_model','mesh':file_receipt(Path(p['mesh'])),
                'shadow_categories':p['selected_categories']} ]})
    atomic_json(output/'pilot_matches.json',{'initial_selection':[],'object_matches':rows,
        'scope':'New native Dexonomy model pilot; asset keys are not Bench2Dex identities'})
    lines=['# 本地 Shadow→Wuji 可扩展资源','',
        f"网格 {len(objects)}；带 Shadow 来源 {len(ready)}；原已映射来源 {len(used)}；新增来源 {len(new)}。",'',
        '| 新模型试验 | 类别 | 握法数 |','| --- | --- | ---: |']
    for p in pilot:lines.append(f"| {p['object']} | {p['family']} | {len(p['selected_categories'])} |")
    lines+=['','这些是本地可用来源，不是已通过静态/重力筛选的模型数。']
    (output/'inventory.md').write_text('\n'.join(lines)+'\n')
    return {k:v for k,v in report.items() if k not in ['objects','pilot','limitations']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--object-root',type=Path,default=Path('assets/object'))
    parser.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v4/expansion_inventory_2026-10-15'))
    args=parser.parse_args();print(json.dumps(inventory(args.object_root,args.batch,args.output),ensure_ascii=False),flush=True)
