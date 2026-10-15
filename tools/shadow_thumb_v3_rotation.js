const data = JSON.parse(document.getElementById('data').textContent);
const $ = id => document.getElementById(id);
const phases = {pregrasp:'预抓取',grasp:'抓取',squeeze:'收紧'};
const state = {entry:null,phase:'grasp',mode:'scene',yaw:0,pitch:2,roll:0,history:false,sequence:0};
if(new URLSearchParams(location.search).get('mode')==='hand')state.mode='hand';
const cache = new Map();
let draggingCanvas = null;
const wrap = (value, count) => ((value % count) + count) % count;
const entries = new Map(data.entries.map(e=>[e.entryId,e]));
const assets = [...new Map(data.entries.map(e=>[e.asset,e.assetLabel])).entries()];
for(const [value,label] of assets){const option=new Option(label,value);$('asset').add(option)}
$('counts').textContent = `${data.scope==='pilot'?'代表样本预览 · ':''}资产 ${assets.length} · 握法条目 ${data.entries.length} · 独立来源 ${data.caseCount} · 每来源 360 个比较帧`;
if(data.back)$('back').href=data.back;
function framePath(entry,phase){return `frames/${entry.caseId}/${phase}_${state.mode}_p${String(state.pitch).padStart(2,'0')}_y${String(state.yaw).padStart(2,'0')}.webp`}
function loadFrame(path){
  if(!cache.has(path)){
    const promise = new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('无法加载 '+path));image.src=path});
    cache.set(path,promise);promise.catch(()=>cache.delete(path));
    while(cache.size>12)cache.delete(cache.keys().next().value);
  }
  return cache.get(path);
}
function updateControls(){
  state.yaw=wrap(state.yaw,data.azimuths.length);state.roll=wrap(state.roll,12);
  state.pitch=Math.max(0,Math.min(data.elevations.length-1,state.pitch));
  for(const key of ['yaw','pitch','roll'])$(key+'Range').value=state[key];
  $('yawCount').textContent=`${data.azimuths[state.yaw]}° · ${state.yaw+1} / ${data.azimuths.length}`;
  $('pitchCount').textContent=`${data.elevations[state.pitch]}° · ${state.pitch+1} / ${data.elevations.length}`;
  $('rollCount').textContent=`${state.roll*30}°`;
  $('scene').classList.toggle('active',state.mode==='scene');$('hand').classList.toggle('active',state.mode==='hand');
}
function element(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el}
function drag(canvas){
  let start;
  canvas.addEventListener('pointerdown',event=>{start={x:event.clientX,y:event.clientY,yaw:state.yaw,pitch:state.pitch};draggingCanvas=canvas;canvas.setPointerCapture(event.pointerId)});
  canvas.addEventListener('pointermove',event=>{
    if(!start||!canvas.hasPointerCapture(event.pointerId))return;
    const yaw=wrap(start.yaw+Math.round((start.x-event.clientX)/24),data.azimuths.length);
    const pitch=Math.max(0,Math.min(data.elevations.length-1,start.pitch+Math.round((start.y-event.clientY)/36)));
    if(yaw!==state.yaw||pitch!==state.pitch){state.yaw=yaw;state.pitch=pitch;render()}
  });
  const stop=()=>{start=null;if(draggingCanvas===canvas)draggingCanvas=null};
  canvas.addEventListener('pointerup',stop);canvas.addEventListener('pointercancel',stop);
}
function paint(canvas,image,role,roll){
  const width=data.width,height=data.height;canvas.width=width;canvas.height=height;
  if(image.naturalWidth!==width*3||image.naturalHeight!==height)throw new Error('比较帧尺寸不匹配');
  const ctx=canvas.getContext('2d');if(!ctx)throw new Error('浏览器无法显示二维画面');
  const angle=roll*Math.PI/6,c=Math.abs(Math.cos(angle)),s=Math.abs(Math.sin(angle));
  const scale=Math.min(width/(width*c+height*s),height/(width*s+height*c));
  ctx.fillStyle='#000';ctx.fillRect(0,0,width,height);ctx.save();ctx.translate(width/2,height/2);ctx.rotate(angle);ctx.scale(scale,scale);
  ctx.drawImage(image,role*width,0,width,height,-width/2,-height/2,width,height);ctx.restore();
}
async function render(){
  if(!state.entry)return;
  updateControls();const sequence=++state.sequence,entry=state.entry;
  const selectedPhases=state.phase==='all'?Object.keys(phases):[state.phase];
  const paths=selectedPhases.map(phase=>framePath(entry,phase));
  const roles=state.history?[0,1,2]:[0,2];
  const snapshot={mode:state.mode,yaw:state.yaw,pitch:state.pitch,roll:state.roll};
  $('loading').textContent='正在加载视角…';
  $('meta').textContent=`${entry.assetLabel} · ${entry.categoryLabel} · ${entry.status==='kinematic_candidate'?'静态检查通过':'需要调整'} · ${entry.versionLabel} · ${entry.physicalPassed===true?'动力学保持检查通过':entry.physicalPassed===false?'动力学保持检查未通过':'动力学未验证'} · 来源：${entry.source} · ${entry.matchLabel}`;
  $('meta').classList.toggle('rejected',entry.status!=='kinematic_candidate');
  try{
    const images=await Promise.all(paths.map(loadFrame));if(sequence!==state.sequence)return;
    const fragment=document.createDocumentFragment();
    for(let i=0;i<selectedPhases.length;i++){
      const phase=selectedPhases[i];fragment.append(element('h2',phases[phase]));
      const grid=element('div');grid.className='grid'+(state.history?' with-history':'');
      const selectedLabel=entry.selectedVersion==='v2_retained'?'最终 Wuji（沿用 V2）':entry.selectedVersion==='v3_rejected'?'最终 Wuji 提案（待修正）':'最终 Wuji（V3）';
      const labels=['原 Shadow','历史 V2',selectedLabel];
      for(const role of roles){
        const label=labels[role];
        const article=element('article');article.className=['source','v2','selected'][role];article.append(element('h3',label));
        const canvas=element('canvas');canvas.dataset.role=String(role);canvas.dataset.phase=phase;canvas.dataset.path=paths[i];
        canvas.dataset.yaw=String(snapshot.yaw);canvas.dataset.pitch=String(snapshot.pitch);canvas.dataset.roll=String(snapshot.roll);
        canvas.setAttribute('aria-label',phases[phase]+' · '+label);paint(canvas,images[i],role,snapshot.roll);drag(canvas);article.append(canvas);grid.append(article);
      }
      fragment.append(grid);
    }
    // Keep drag targets alive while a pointer is captured, then replace on release.
    const active=draggingCanvas?.isConnected?draggingCanvas:null;
    if(active){
      const current=[...$('panels').querySelectorAll('canvas')];
      if(current.length===selectedPhases.length*roles.length&&current.every(c=>selectedPhases.includes(c.dataset.phase)&&roles.includes(Number(c.dataset.role)))){
        for(const canvas of current){const i=selectedPhases.indexOf(canvas.dataset.phase),role=Number(canvas.dataset.role);paint(canvas,images[i],role,snapshot.roll);canvas.dataset.path=paths[i];canvas.dataset.yaw=String(snapshot.yaw);canvas.dataset.pitch=String(snapshot.pitch);canvas.dataset.roll=String(snapshot.roll)}
      }else $('panels').replaceChildren(fragment);
    }else $('panels').replaceChildren(fragment);
    $('loading').textContent='';$('panels').dataset.sequence=String(sequence);
  }catch(error){if(sequence===state.sequence)$('loading').textContent=error.message}
}
function chooseEntry(id){
  state.entry=entries.get(id)||data.entries[0];$('asset').value=state.entry.asset;
  $('grasp').replaceChildren();for(const e of data.entries.filter(e=>e.asset===state.entry.asset))$('grasp').add(new Option(e.categoryLabel,e.entryId));
  $('grasp').value=state.entry.entryId;history.replaceState(null,'','#'+encodeURIComponent(state.entry.entryId));render();
}
$('asset').onchange=()=>chooseEntry(data.entries.find(e=>e.asset===$('asset').value).entryId);
$('grasp').onchange=()=>chooseEntry($('grasp').value);
$('history').ontoggle=()=>{state.history=$('history').open;render()};
$('phase').onchange=()=>{state.phase=$('phase').value;render()};
for(const mode of ['scene','hand'])$(mode).onclick=()=>{state.mode=mode;render()};
for(const [key,delta] of [['yaw',-1],['yaw',1],['pitch',-1],['pitch',1],['roll',-1],['roll',1]]){
  $(key+(delta<0?'Previous':'Next')).onclick=()=>{state[key]+=delta;render()};
}
for(const key of ['yaw','pitch','roll'])$(key+'Range').oninput=event=>{state[key]=Number(event.target.value);render()};
$('reset').onclick=()=>{state.yaw=0;state.pitch=2;state.roll=0;render()};
let id;try{id=decodeURIComponent(location.hash.slice(1))}catch(_){id=''}
chooseEntry(id);
