#!/usr/bin/env python3
"""Offline Source / V1 / selected V2 review, including non-adopted proposals."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json
from tools.review_shadow_wuji_batch import PAGE,ASSET_NAMES,CATEGORY_NAMES,reason_label


def selection_label(reason):
    labels={'baseline_geometry_preserved':'保护第一版已通过的静态质量',
            'thumb_improvement_below_threshold':'拇指改善不足',
            'proposal_geometry_still_rejected':'提案仍未通过静态筛选',
            'thumb_fidelity_improved_with_geometry_pass':'拇指指标改善且静态筛选通过'}
    if reason.startswith('thumb_component_regression_'):return '拇指单项指标出现退化'
    if reason.startswith('thumb_phase_regression_'):return '拇指某阶段出现退化'
    return labels.get(reason,reason)


def build(root):
    root=Path(root);plan=json.loads((root/'plan.json').read_text())
    summary=json.loads((root/'summary.json').read_text())
    rows={r['case_id']:r for r in summary['results']};jobs={j['case_id']:j for j in plan['jobs']}
    entries=[]
    matches={'same_ycb_id_and_name':'同 YCB 编号/名称，网格等价待核查','same_named_category':'同名类别候选','similar_geometry_family':'相近几何家族候选'}
    md=['# 拇指第二版与第一版逐目标对照','',
        '| 资产 | 握法 | 选用版本 | 原拇指误差 | 选用拇指误差 | 静态状态 |','| --- | --- | --- | ---: | ---: | --- |']
    for asset in plan['assets']:
        for grasp in asset['entries']:
            cid=grasp['case_id'];job=jobs[cid];row=rows.get(cid,{})
            folder=root/'samples'/cid;path=folder/'result.json';report=json.loads(path.read_text()) if path.is_file() else None
            def relative(name):
                p=folder/name
                return p.relative_to(root).as_posix() if p.is_file() else None
            def average_thumb(key,version):
                return sum(m[key] for m in report[version].values())/3 if report else None
            name=asset['bench_object'];prefix=name.split('_')[0].split('-')[0]
            geometry=report['selected_quality'] if report else None
            penetration=max(max(m['max_hand_object_penetration_m'],m['max_self_penetration_m']) for m in geometry['phases'].values())*1000 if report else None
            version=row.get('selected_version','pending')
            proposal=relative('proposal/comparison.png')
            fallback_proposal=relative('fallback_trial/proposal/comparison.png')
            entry={'asset':name,'assetLabel':ASSET_NAMES.get(prefix,name)+' · '+name,
                'category':grasp['category'],'categoryLabel':CATEGORY_NAMES.get(grasp['category'].split('_')[0],grasp['category'])+' · '+grasp['category'],
                'source':job['selection']['dexonomy_object'],'status':row.get('status','pending'),
                'matchLabel':matches.get(asset['match_level'],asset['match_level']),
                'image':relative('comparison.png'),'handImage':relative('hand_only/comparison.png'),
                'result':relative('result.json') or relative('failure.json'),'postures':relative('postures.npz'),
                'shape':geometry['phases']['grasp']['mean_shape_error'] if geometry else None,
                'transition':max(geometry['transition_errors']) if geometry else None,'penetration':penetration,
                'terminationLabel':{'converged':'收敛','evaluation_limit':'达到迭代预算','time_budget_checkpoint':'时间预算检查点'}.get(row.get('solver_termination'),row.get('solver_termination','—')),
                'reasons':[reason_label(s) for s in row.get('failure_reasons',[])],'error':row.get('error'),
                'selectedVersion':version,'versionLabel':'采用第二版' if version=='v2' else '保留第一版' if version=='v1_retained' else '处理中',
                'thumbBefore':average_thumb('score','baseline_thumb'),'thumbAfter':average_thumb('score','selected_thumb'),
                'padBefore':average_thumb('pad_angle_deg','baseline_thumb'),'padAfter':average_thumb('pad_angle_deg','selected_thumb'),
                'proposal':proposal,'fallbackProposal':fallback_proposal,
                'selectionReason':selection_label(row.get('selection_reason','')),'attemptCount':row.get('attempt_count',0)}
            entries.append(entry)
            md.append(f'| {name} | {grasp["category"]} | {version} | {entry["thumbBefore"]} | {entry["thumbAfter"]} | {entry["status"]} |')
    data={'assetCount':plan['asset_count'],'uniqueCases':plan['unique_source_cases'],'completedCases':summary['completed_source_cases'],
          'candidateEntries':sum(e['status']=='kinematic_candidate' for e in entries),
          'rejectedEntries':sum(e['status']=='kinematic_rejected' for e in entries),
          'deferredCount':len(plan['deferred_assets']),'entries':entries}
    page=PAGE.replace('全资产姿态审查','拇指 V1 / V2 对照')
    page=page.replace('顶行 Shadow 来源，中行 Wuji 迁移初值，底行 Wuji 联合优化','顶行 Shadow 来源，中行第一版优化结果，底行本次选用结果')
    page=page.replace('当前使用 Dexonomy 来源物体与尺度，目标是 Wuji 一代右手。','采用第二版表示拇指专门指标改善且检查通过；未采用时保留第一版，并提供提案图。指腹方向是几何推断的参考，尚非硬件标定。当前使用 Dexonomy 来源物体与尺度，目标是 Wuji 一代右手。')
    page=page.replace('手型和阶段动作误差按指长归一化，无单位；穿透使用毫米。','拇指综合误差和参考指腹角度为三个阶段的平均值；单阶段和分项数据见详细指标。手型和阶段动作误差按指长归一化，无单位；穿透使用毫米。')
    page=page.replace('<input id="search"','<select id="version"><option value="">全部选用版本</option><option value="v2">采用第二版</option><option value="v1_retained">保留第一版</option></select><input id="search"')
    page=page.replace("const entries=data.entries.filter(e=>","const entries=data.entries.filter(e=>(!$('version').value||e.selectedVersion===$('version').value)&&")
    page=page.replace("['asset','status','search']","['asset','status','version','search']")
    page=page.replace("title.append(elem('span',labels[e.status],`badge ${e.status}`));", "title.append(elem('span',labels[e.status],`badge ${e.status}`));title.append(elem('span',' · '+e.versionLabel));")
    page=page.replace("if(e.shape!==null){", "if(e.thumbBefore!==null){const tm=elem('div',undefined,'metrics');tm.append(elem('div','拇指综合误差：'+e.thumbBefore.toFixed(3)+' → '+e.thumbAfter.toFixed(3)),elem('div','参考指腹方向误差：'+e.padBefore.toFixed(1)+'° → '+e.padAfter.toFixed(1)+'°'));d.append(tm)}if(e.shape!==null){")
    page=page.replace("d.append(links);card.append(d);", "if(e.proposal)links.append(link('未采用的主提案',e.proposal));if(e.fallbackProposal)links.append(link('未采用的保守提案',e.fallbackProposal));d.append(links);if(e.selectedVersion==='v1_retained')d.append(elem('div','保留原因：'+e.selectionReason,'source'));card.append(d);")
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<',r'\u003c')
    (root/'index.html').write_text(page.replace('__DATA__',payload),encoding='utf-8')
    atomic_json(root/'review.json',data);(root/'summary.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v2/all_matched_thumb_v2'))
    args=parser.parse_args();r=build(args.batch)
    print(json.dumps({k:v for k,v in r.items() if k!='entries'},ensure_ascii=False))
