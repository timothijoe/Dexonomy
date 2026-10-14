#!/usr/bin/env python3
"""Copy only the selected local objects, scenes and Shadow records for review."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json, sha256


def stage(selection_path,object_root,output):
    if output.exists():raise ValueError('Output exists; use a new directory')
    report=json.loads(selection_path.read_text())
    object_root=object_root.resolve()
    output.mkdir(parents=True)
    identities=[];objects=set()
    def copy_file(source,destination):
        expected=sha256(source)
        if destination.exists():
            if sha256(destination)!=expected:raise ValueError('Conflicting staged resource')
            return
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        if sha256(destination)!=expected:raise ValueError('Copy checksum mismatch')
        identities.append({'source':str(source),'path':str(destination.relative_to(output)), 'sha256':expected})
    for selected in report['initial_selection']:
        if selected['status']!='source_extracted_not_transferred':continue
        source=Path(selected['source']['path'])
        if sha256(source)!=selected['source']['sha256']:raise ValueError('Source checksum changed')
        matching=next(c for row in report['object_matches'] for c in row['candidates'] if c['dexonomy_object']==selected['dexonomy_object'])
        name=selected['dexonomy_object'];dataset=matching['dataset'];objects.add((dataset,name))
        root=object_root/dataset/'processed_data'/name
        for path in sorted(root.rglob('*')):
            if path.is_file():copy_file(path,output/'assets/object'/path.relative_to(object_root))
        copy_file(source,output/'assets/object'/source.resolve().relative_to(object_root))
        scene=Path(selected['scene_path']).resolve()
        copy_file(scene,output/'assets/object'/scene.relative_to(object_root))
        if selected.get('bench_geometry'):
            mesh=Path(selected['bench_geometry']['mesh']['path'])
            copy_file(mesh,output/'bench_meshes'/(selected['bench_object']+'.obj'))
    atomic_json(output/'resources.json',{'schema_version':1,'selection_sha256':sha256(selection_path),
                                        'unique_dexonomy_objects':len(objects),'file_count':len(identities),
                                        'files':identities,'note':'Asset subset only, not a standalone simulator or successful task dataset'})
    (output/'README.md').write_text('# Shadow→Wuji 首批资产子集\n\n'
        f'独立 Dexonomy 对象 {len(objects)}；复制文件 {len(identities)}，逐文件 SHA-256 验证通过。\n\n'
        'assets/object 保持原对象、场景与选定 Shadow NPY 的相对布局；bench_meshes 为已经可用的 Bench2Dex USD 导出网格。'
        'objects 与抓取候选身份见上层选择清单；本目录不代表已完成模型等价验证或动力学迁移。\n')
    return {'unique_dexonomy_objects':len(objects),'file_count':len(identities)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',type=Path,default=Path('output/shadow_wuji_v1/asset_selection_v2/matches.json'))
    parser.add_argument('--object-root',type=Path,default=Path('assets/object'))
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v1/selected_assets'))
    args=parser.parse_args()
    print(json.dumps(stage(args.selection,args.object_root,args.output),indent=2))
