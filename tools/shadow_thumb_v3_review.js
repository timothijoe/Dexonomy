const data=JSON.parse(document.getElementById('data').textContent);
const $=id=>document.getElementById(id);
const labels={kinematic_candidate:'静态筛选通过',kinematic_rejected:'需要调整',error:'输入或执行问题',pending:'尚未处理'};
const phases=['预抓取','抓取','收紧'];
let mode='object', modalImage=null, modalSequence=0;
const camera={yaw:0,pitch:2,roll:0};
const imageCache=new Map();
const wrap=(value,count)=>((value%count)+count)%count;
function elem(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n}
function link(label,url){const a=elem('a',label);a.href=url;a.target='_blank';a.rel='noopener';return a}
const assets=[...new Map(data.entries.map(e=>[e.asset,e.assetLabel])).entries()];
for(const [id,label]of assets)$('asset').append(new Option(label,id));
$('counts').textContent=`资产 ${data.assetCount} · 握法条目 ${data.entries.length} · 独立迁移 ${data.completedCases}/${data.uniqueCases} · 静态筛选通过 ${data.candidateEntries} · 待调整 ${data.rejectedEntries} · 缺口资产 ${data.deferredCount}`;
$('rotationLink').hidden=!data.entries.some(e=>e.rotation);
function finalLabel(e){return e.selectedVersion==='v2_retained'?'最终 Wuji（沿用 V2）':e.selectedVersion==='v3_rejected'?'最终 Wuji 提案（待修正）':'最终 Wuji（V3）'}
function loadImage(url){
  if(!imageCache.has(url)){
    const promise=new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('对照图加载失败：'+url));image.src=url});
    imageCache.set(url,promise);promise.catch(()=>imageCache.delete(url));
    while(imageCache.size>60)imageCache.delete(imageCache.keys().next().value);
  }
  return imageCache.get(url);
}
async function loadComparison(entry){
  const snapshot={...camera};
  if(data.camera&&entry.rotationCase){
    const urls=['pregrasp','grasp','squeeze'].map(phase=>`rotation/frames/${entry.rotationCase}/${phase}_${mode==='object'?'scene':'hand'}_p${String(snapshot.pitch).padStart(2,'0')}_y${String(snapshot.yaw).padStart(2,'0')}.webp`);
    return {images:await Promise.all(urls.map(loadImage)),urls,rotation:true,snapshot};
  }
  const url=mode==='object'?entry.image:entry.handImage;
  return {images:[await loadImage(url)],urls:[url],rotation:false,snapshot};
}
function comparison(loaded,entry,zoom){
  const view=elem('div',undefined,'comparison');
  const roles=$('history').open?[0,1,2]:[0,2];
  const titles=['原 Shadow','历史 V2',finalLabel(entry)];
  for(let phase=0;phase<3;phase++){
    view.append(elem('h4',phases[phase]));
    const grid=elem('div',undefined,'posture-grid'+($('history').open?' with-history':''));
    const image=loaded.images[loaded.rotation?phase:0];
    const width=loaded.rotation?data.camera.width:640,height=loaded.rotation?data.camera.height:435;
    if(image.naturalWidth!==(loaded.rotation?width*3:1920)||image.naturalHeight!==(loaded.rotation?height:1440))throw new Error('三阶段对照图尺寸不匹配');
    for(const role of roles){
      const figure=elem('figure'),canvas=elem('canvas');
      figure.append(elem('figcaption',titles[role]));canvas.width=width;canvas.height=height;
      canvas.dataset.role=String(role);canvas.dataset.phase=String(phase);canvas.dataset.path=loaded.urls[loaded.rotation?phase:0];
      for(const key of ['yaw','pitch','roll'])canvas.dataset[key]=String(loaded.snapshot[key]);
      canvas.setAttribute('aria-label',phases[phase]+' · '+titles[role]);
      const ctx=canvas.getContext('2d'),angle=loaded.snapshot.roll*Math.PI/6,c=Math.abs(Math.cos(angle)),s=Math.abs(Math.sin(angle));
      const scale=Math.min(width/(width*c+height*s),height/(width*s+height*c));
      ctx.fillStyle='#000';ctx.fillRect(0,0,width,height);ctx.translate(width/2,height/2);ctx.rotate(angle);ctx.scale(scale,scale);
      const sx=loaded.rotation?role*width:phase*640,sy=loaded.rotation?0:role*480+45;
      ctx.drawImage(image,sx,sy,width,height,-width/2,-height/2,width,height);
      if(zoom)canvas.onclick=()=>{modalImage={entry};$('large').replaceChildren(comparison(loaded,entry,false));$('modalCameraControls').hidden=!(data.camera&&entry.rotationCase);$('modal').classList.add('open')};
      figure.append(canvas);grid.append(figure);
    }
    view.append(grid);
  }
  return view;
}
async function refreshModal(){
  if(!modalImage)return;
  const sequence=++modalSequence,entry=modalImage.entry;
  try{const loaded=await loadComparison(entry);if(sequence===modalSequence&&modalImage)$('large').replaceChildren(comparison(loaded,entry,false))}
  catch(error){if(sequence===modalSequence&&modalImage)$('large').textContent=error.message}
}
function cameraControls(container,prefix){
  const defs=[['yaw','水平环绕（Yaw）','←','→',11],['pitch','上下俯仰（Pitch）','↓','↑',4],['roll','画面滚转（Roll）','↶','↷',11]];
  for(const [key,title,previous,next,max] of defs){
    const control=elem('div',undefined,'camera-control'),label=elem('label',title),row=elem('div',undefined,'camera-row');
    const before=elem('button',previous),after=elem('button',next),range=elem('input'),output=elem('output');
    range.type='range';range.min=0;range.max=max;range.id=prefix+key+'Range';label.htmlFor=range.id;output.id=prefix+key+'Count';
    before.id=prefix+key+'Previous';after.id=prefix+key+'Next';before.setAttribute('aria-label',title+'减少');after.setAttribute('aria-label',title+'增加');
    before.onclick=()=>changeCamera(key,camera[key]-1);after.onclick=()=>changeCamera(key,camera[key]+1);range.oninput=()=>changeCamera(key,Number(range.value));
    row.append(before,range,after);control.append(label,row,output);container.append(control);
  }
}
function updateCameraControls(){
  for(const prefix of ['', 'modal'])for(const key of ['yaw','pitch','roll']){
    $(prefix+key+'Range').value=camera[key];
    $(prefix+key+'Count').textContent=(key==='roll'?camera.roll*30:key==='yaw'?data.camera.azimuths[camera.yaw]:data.camera.elevations[camera.pitch])+'°';
  }
}
function changeCamera(key,value){
  camera[key]=key==='pitch'?Math.max(0,Math.min(data.camera.elevations.length-1,value)):wrap(value,key==='yaw'?data.camera.azimuths.length:12);
  updateCameraControls();show();refreshModal();
}
if(data.camera){cameraControls($('cameraControls'),'');cameraControls($('modalCameraControls'),'modal');$('cameraControls').hidden=false;updateCameraControls()}
else $('cameraNote').hidden=false;
const observer=new IntersectionObserver(items=>{for(const item of items)if(item.isIntersecting){observer.unobserve(item.target);item.target.loadComparison()}},{rootMargin:'400px'});
function picture(entry,url){
  const holder=elem('div','正在加载对照…','placeholder');holder.dataset.path=url;
  let pending=false;
  holder.loadComparison=async()=>{
    if(pending)return;pending=true;
    try{const loaded=await loadComparison(entry);if(holder.isConnected)holder.replaceWith(comparison(loaded,entry,true))}
    catch(error){if(holder.isConnected)holder.textContent=error.message}
  };
  return holder;
}
function show(){
  observer.disconnect();
  const entries=data.entries.filter(e=>(!$('asset').value||e.asset===$('asset').value)&&(!$('status').value||e.status===$('status').value)&&(!$('version').value||e.selectedVersion===$('version').value)&&(!$('search').value||[e.assetLabel,e.category,e.categoryLabel,e.source].join(' ').toLowerCase().includes($('search').value.toLowerCase())));
  $('cards').replaceChildren();$('empty').style.display=entries.length?'none':'block';
  for(const e of entries){
    const card=elem('article');card.append(elem('h2',e.assetLabel));
    const title=elem('h3',e.categoryLabel+' · ');title.append(elem('span',labels[e.status],`badge ${e.status}`));card.append(title);
    const url=mode==='object'?e.image:e.handImage;
    if(url){const holder=picture(e,url);card.append(holder);observer.observe(holder)}else card.append(elem('div','对照图未生成','placeholder'));
    const d=elem('div',undefined,'details');
    d.append(elem('div','结果来源：'+e.versionLabel),elem('div',e.physicalPassed===true?'动力学检查通过':e.physicalPassed===false?'动力学检查未通过':'动力学未验证'),elem('div','来源：'+e.source,'source'),elem('div','对应关系：'+e.matchLabel,'source'));
    if(e.maxOrientedAngle!==null){const n=elem('div',undefined,'metrics');n.append(elem('div','末端最大有向夹角：'+e.maxOrientedAngle.toFixed(1)+'°'),elem('div','最大组合弯曲：'+e.maxCombinedBend.toFixed(1)+'°'),elem('div','最大指段方向误差：'+e.maxBoneError.toFixed(1)+'°'),elem('div','最大参考指腹方向误差：'+e.maxPadError.toFixed(1)+'°'));d.append(n)}
    if(e.shape!==null){const m=elem('div',undefined,'metrics');m.append(elem('div','抓取手型误差：'+e.shape.toFixed(3)),elem('div','阶段动作误差：'+e.transition.toFixed(3)),elem('div','最大穿透：'+e.penetration.toFixed(2)+' mm'),elem('div','求解停止：'+e.terminationLabel));d.append(m)}
    if(e.reasons.length)d.append(elem('div',e.reasons.join('；'),'reason'));if(e.error)d.append(elem('div',e.error,'reason'));
    if(e.phaseAngles.length){const angles=elem('details');angles.append(elem('summary','三阶段夹角：V2 → 最终（伸直 180°）'));for(const p of e.phaseAngles)angles.append(elem('div',p.phase+'：关节3 '+p.before[0].toFixed(1)+'° → '+p.after[0].toFixed(1)+'°；关节4 '+p.before[1].toFixed(1)+'° → '+p.after[1].toFixed(1)+'°'));d.append(angles)}
    const links=elem('div',undefined,'links');
    if(e.result)links.append(link('详细指标',e.result));if(e.postures)links.append(link('三阶段姿态 NPZ',e.postures));
    if(e.rotation)links.append(link('旋转查看',e.rotation.replace('#','?mode='+(mode==='object'?'scene':'hand')+'#')));
    const history=elem('details');history.append(elem('summary','历史文件与优化尝试'));
    const historyLinks=elem('div',undefined,'links');
    if(url)historyLinks.append(link('原三版本九格图',url));if(e.proposal)historyLinks.append(link('未采用的第三版提案',e.proposal));if(e.primaryTrial)historyLinks.append(link('首轮结果',e.primaryTrial));if(e.repairTrial)historyLinks.append(link('几何修复尝试',e.repairTrial));history.append(historyLinks);
    d.append(links,history);card.append(d);$('cards').append(card);
  }
}
for(const id of ['asset','status','version','search'])$(id).addEventListener(id==='search'?'input':'change',show);
$('history').ontoggle=()=>{show();refreshModal()};
$('withObject').onclick=()=>{mode='object';$('withObject').classList.add('active');$('handOnly').classList.remove('active');show()};
$('handOnly').onclick=()=>{mode='hand';$('handOnly').classList.add('active');$('withObject').classList.remove('active');show()};
function closeModal(){$('modal').classList.remove('open');$('large').replaceChildren();modalImage=null;modalSequence++}
$('close').onclick=closeModal;$('modal').onclick=e=>{if(e.target===$('modal'))closeModal()};
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});show();
