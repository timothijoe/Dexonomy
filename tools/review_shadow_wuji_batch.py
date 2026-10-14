#!/usr/bin/env python3
"""Build a standalone, offline asset/grasp review page from real batch results."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json

ASSET_NAMES={
 '002':'主厨罐头','008':'布丁盒','009':'明胶盒','010':'肉罐头','011':'香蕉','013':'苹果','014':'柠檬','017':'橙子',
 '021':'清洁剂瓶','024':'碗','025':'马克杯','029':'盘子','036':'木块','043':'十字螺丝刀','044':'一字螺丝刀',
 '048':'锤子','053':'迷你足球','054':'垒球','055':'棒球','056':'网球','057':'壁球','058':'高尔夫球','065':'杯子',
 '080':'瓶子','098':'键盘','105':'鼠标','111':'冰箱模型','122':'垃圾桶','129':'鞋盒','130':'托盘','144':'乒乓球',
 '146':'橄榄油瓶','147':'电钻','151':'牛奶盒','153':'鞋','154':'木箱','166':'记号笔','167':'笔筒','168':'电池',
 '169':'塑料盒','171':'味精容器','172':'酱油瓶','173':'醋瓶','183':'面包篮','186':'药瓶','189':'刷子','194':'酒杯',
 '199':'胶水容器','200':'清洁剂','203':'印章','209':'香皂','211':'护肤油瓶','218':'牙膏','221':'笔','223':'平底锅',
 '224':'酒瓶','325':'钢琴模型','326':'拼图模型'}
CATEGORY_NAMES={
 '1':'大直径握持','2':'小直径握持','3':'中等包握','5':'轻型工具握持','6':'四指棱柱握持','7':'三指棱柱握持',
 '8':'两指棱柱握持','9':'掌侧捏持','10':'盘形包握','11':'球形包握','12':'盘形精细抓取','13':'球形指尖抓取',
 '14':'三指抓取','15':'固定钩握','16':'侧向抓取','20':'书写三指抓取','24':'指尖捏持','26':'四指球形抓取','29':'棒状握持'}


def reason_label(reason):
    if reason=='stage_action_deviation':return '阶段动作变化偏差较大'
    phases={'pregrasp':'预抓取','grasp':'抓取','squeeze':'收紧'}
    meanings={'penetration':'穿透过大','shape_deviation':'手型偏差较大',
              'action_deviation':'相对中性动作偏差较大','required_contact_missing':'必要接触不足'}
    for prefix,phase in phases.items():
        if reason.startswith(prefix+'_'):return phase+'：'+meanings.get(reason[len(prefix)+1:],reason)
    return reason


PAGE=r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shadow → Wuji 一代 · 全资产姿态审查</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#10151e;color:#e7ecf5}*{box-sizing:border-box}
body{margin:0}header{padding:26px 28px 16px;border-bottom:1px solid #344056}h1{font-size:25px;margin:0 0 12px}
p{line-height:1.65;margin:9px 0;color:#b7c4d8}#counts{font-size:15px;color:#8dd9ff}.toolbar{padding:18px 28px;display:flex;gap:12px;flex-wrap:wrap;position:sticky;top:0;background:#10151ef2;z-index:2}
select,input,button{font:inherit;background:#1c2635;color:#e7ecf5;border:1px solid #42516b;border-radius:7px;padding:9px 12px}input{min-width:240px}
button{cursor:pointer}button.active{background:#285375;border-color:#80cbff}main{padding:0 28px 28px;display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px}
article{border:1px solid #344056;background:#17202d;border-radius:10px;overflow:hidden}article h2{font-size:18px;margin:15px 16px 8px}article h3{font-size:15px;font-weight:500;color:#ccd9eb;margin:0 16px 12px}
.badge{font-size:12px;padding:3px 8px;border-radius:20px;display:inline-block}.kinematic_candidate{background:#244734;color:#a1efbd}.kinematic_rejected{background:#563e24;color:#ffcf8e}.error{background:#582b32;color:#ffb1ba}.pending{background:#303a4b;color:#bac6d8}
.photo{width:100%;display:block;cursor:zoom-in;background:#080c12;aspect-ratio:4/3;object-fit:contain}.placeholder{aspect-ratio:4/3;display:grid;place-items:center;color:#8593a9;background:#080c12}
.details{padding:13px 16px;line-height:1.6;font-size:13px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:6px}a{color:#91d5ff}.reason{color:#ffc09a;overflow-wrap:anywhere}.source{color:#aab8cc;font-size:12px;overflow-wrap:anywhere}.links{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px}#empty{padding:30px;display:none}
#modal{position:fixed;inset:0;background:#000e;z-index:5;display:none;overflow:auto;padding:24px}#modal.open{display:block}#modal img{display:block;max-width:100%;height:auto;margin:auto}#modal button{position:fixed;right:20px;top:15px;z-index:6}.footer{padding:18px 28px;color:#93a2b7;font-size:12px}
@media(max-width:600px){header,.toolbar{padding:16px}main{padding:0 12px;grid-template-columns:1fr}input{min-width:160px;width:100%}}
</style>
<header><h1>Shadow → Wuji 一代 · 全资产姿态审查</h1><div id="counts"></div>
<p>每个资产 3–4 种来源握法。图中依次为：顶行 Shadow 来源，中行 Wuji 迁移初值，底行 Wuji 联合优化；列为预抓取、抓取、收紧。</p>
<p>当前使用 Dexonomy 来源物体与尺度，目标是 Wuji 一代右手。静态姿态已生成不代表真实控制下已经握住；缺少来源的资产本轮保留为缺口。</p></header>
<div class="toolbar"><select id="asset"><option value="">全部资产</option></select><select id="status"><option value="">全部状态</option><option value="kinematic_candidate">静态筛选通过</option><option value="kinematic_rejected">需要调整</option><option value="error">输入或执行问题</option><option value="pending">尚未处理</option></select>
<input id="search" placeholder="搜索资产、握法或来源对象"><button id="withObject" class="active">带物体对照</button><button id="handOnly">纯手型对照</button></div>
<main id="cards"></main><div id="empty">没有符合筛选条件的结果。</div><div class="footer">手型和阶段动作误差按指长归一化，无单位；穿透使用毫米。纯手型图按掌心对齐，并保留两手原始尺寸。单击图片放大，Esc 关闭。</div>
<div id="modal"><button id="close">关闭 ×</button><img id="large" alt="三阶段放大对照"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('data').textContent);let mode='object';
const $=id=>document.getElementById(id);const labels={kinematic_candidate:'静态筛选通过',kinematic_rejected:'需要调整',error:'输入或执行问题',pending:'尚未处理'};
const assets=[...new Map(data.entries.map(e=>[e.asset,e.assetLabel])).entries()];
for(const [id,label]of assets){const o=document.createElement('option');o.value=id;o.textContent=label;$('asset').append(o)}
$('counts').textContent=`资产 ${data.assetCount} · 握法条目 ${data.entries.length} · 独立迁移 ${data.completedCases}/${data.uniqueCases} · 静态筛选通过 ${data.candidateEntries} · 待调整 ${data.rejectedEntries} · 缺口资产 ${data.deferredCount}`;
function elem(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n}
function link(label,url){const a=elem('a',label);a.href=url;a.target='_blank';a.rel='noopener';return a}
function show(){const entries=data.entries.filter(e=>(!$('asset').value||e.asset===$('asset').value)&&(!$('status').value||e.status===$('status').value)&&(! $('search').value||[e.assetLabel,e.category,e.categoryLabel,e.source].join(' ').toLowerCase().includes($('search').value.toLowerCase())));$('cards').replaceChildren();$('empty').style.display=entries.length?'none':'block';
for(const e of entries){const card=elem('article');card.append(elem('h2',e.assetLabel));const title=elem('h3',e.categoryLabel+' · ');title.append(elem('span',labels[e.status],`badge ${e.status}`));card.append(title);
const url=mode==='object'?e.image:e.handImage;if(url){const im=elem('img');im.src=url;im.className='photo';im.loading='lazy';im.alt=e.assetLabel+' '+e.categoryLabel+' '+(mode==='object'?'带物体':'纯手型')+'三阶段对照';im.onclick=()=>{$('large').src=url;$('modal').classList.add('open')};card.append(im)}else card.append(elem('div',e.status==='pending'?'等待批次处理':'对照图未生成','placeholder'));
const d=elem('div',undefined,'details');d.append(elem('div','来源：'+e.source,'source'));d.append(elem('div','对应关系：'+e.matchLabel,'source'));
if(e.shape!==null){const m=elem('div',undefined,'metrics');m.append(elem('div','抓取手型误差：'+e.shape.toFixed(3)),elem('div','阶段动作误差：'+e.transition.toFixed(3)),elem('div','最大穿透：'+e.penetration.toFixed(2)+' mm'),elem('div','求解停止：'+e.terminationLabel));d.append(m)}
if(e.reasons.length)d.append(elem('div',e.reasons.join('；'),'reason'));if(e.error)d.append(elem('div',e.error,'reason'));
const links=elem('div',undefined,'links');if(e.result)links.append(link('详细指标',e.result));if(e.postures)links.append(link('三阶段姿态 NPZ',e.postures));if(e.image)links.append(link('打开对照图',url||e.image));d.append(links);card.append(d);$('cards').append(card)}}
for(const id of['asset','status','search'])$(id).addEventListener(id==='search'?'input':'change',show);
$('withObject').onclick=()=>{mode='object';$('withObject').classList.add('active');$('handOnly').classList.remove('active');show()};$('handOnly').onclick=()=>{mode='hand';$('handOnly').classList.add('active');$('withObject').classList.remove('active');show()};
$('close').onclick=()=>$('modal').classList.remove('open');$('modal').onclick=e=>{if(e.target===$('modal'))$('modal').classList.remove('open')};document.addEventListener('keydown',e=>{if(e.key==='Escape')$('modal').classList.remove('open')});show();
</script></html>'''


def build(output):
    output=Path(output)
    plan=json.loads((output/'plan.json').read_text())
    summary=json.loads((output/'summary.json').read_text()) if (output/'summary.json').exists() else {'results':[],'completed_source_cases':0}
    rows={r['case_id']:r for r in summary['results']};jobs={j['case_id']:j for j in plan['jobs']}
    entries=[]
    matches={'same_ycb_id_and_name':'同 YCB 编号/名称，网格等价待核查','same_named_category':'同名类别候选','similar_geometry_family':'相近几何家族候选'}
    terminations={'converged':'收敛','evaluation_limit':'达到迭代预算','time_budget_checkpoint':'时间预算，保留检查点'}
    md=['# Shadow→Wuji 一代全匹配资产批次','',f'资产 {plan["asset_count"]}；握法条目 {plan["coverage_entries"]}；独立来源 {plan["unique_source_cases"]}；已处理 {summary["completed_source_cases"]}。','',
        '以下为静态姿态结果，不是动力学抓取成功率。缺口资产按用户要求延期。','',
        '| 资产 | 握法 | 来源 | 状态 | 抓取手型误差 | 最大穿透 mm |','| --- | --- | --- | --- | ---: | ---: |']
    for asset in plan['assets']:
        for grasp in asset['entries']:
            cid=grasp['case_id'];job=jobs[cid];row=rows.get(cid,{})
            folder=output/'samples'/cid;path=folder/'result.json'
            r=json.loads(path.read_text()) if path.is_file() else None
            shape=transition=penetration=None
            if r:
                m=r['optimized_quality']['phases'];shape=m['grasp']['mean_shape_error']
                transition=max(r['optimized_quality']['transition_errors'])
                penetration=max(max(p['max_hand_object_penetration_m'],p['max_self_penetration_m']) for p in m.values())*1000
            def relative(name):
                p=folder/name
                return p.relative_to(output).as_posix() if p.is_file() else None
            name=asset['bench_object'];prefix=name.split('_')[0].split('-')[0]
            entry={'asset':name,'assetLabel':ASSET_NAMES.get(prefix,name)+' · '+name,
                   'category':grasp['category'],'categoryLabel':CATEGORY_NAMES.get(grasp['category'].split('_')[0],grasp['category'])+' · '+grasp['category'],
                   'source':job['selection']['dexonomy_object'],'status':row.get('status','pending'),
                   'matchLabel':matches.get(asset['match_level'],asset['match_level']),
                   'image':relative('comparison.png'),'handImage':relative('hand_only/comparison.png'),
                   'result':relative('result.json') or relative('failure.json'),'postures':relative('postures.npz'),
                   'shape':shape,'transition':transition,'penetration':penetration,
                   'terminationLabel':terminations.get(row.get('solver_termination'),row.get('solver_termination','—')),
                   'reasons':[reason_label(s) for s in row.get('failure_reasons',[])],'error':row.get('error') or row.get('render_error')}
            entries.append(entry)
            md.append(f'| {name} | {grasp["category"]} | {entry["source"]} | {entry["status"]} | {shape if shape is not None else "—"} | {penetration if penetration is not None else "—"} |')
    data={'assetCount':plan['asset_count'],'uniqueCases':plan['unique_source_cases'],'completedCases':summary['completed_source_cases'],
          'candidateEntries':sum(e['status']=='kinematic_candidate' for e in entries),
          'rejectedEntries':sum(e['status']=='kinematic_rejected' for e in entries),
          'deferredCount':len(plan['deferred_assets']),'entries':entries}
    atomic_json(output/'review.json',data)
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<',r'\u003c')
    (output/'index.html').write_text(PAGE.replace('__DATA__',payload),encoding='utf-8')
    (output/'summary.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v1/all_matched_batch_v1'))
    args=parser.parse_args();r=build(args.batch)
    print(json.dumps({k:v for k,v in r.items() if k!='entries'},ensure_ascii=False))
