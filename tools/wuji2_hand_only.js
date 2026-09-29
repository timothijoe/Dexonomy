const PHASES = {pregrasp:'预抓取',grasp:'抓取',squeeze:'收紧'};
const FINGERS = {thumb:'拇指',index:'食指',middle:'中指',ring:'无名指',pinky:'小指'};
const state = {index:null,caseId:null,phase:'grasp',view:0,mode:'image',yaw:0,pitch:2,roll:0,
               viewerReady:false,realtimeUnavailable:false};
const el = id => document.getElementById(id);
const roles = ['source','wuji'];
let viewerModule;
const timers = new Map();

function currentCase(){return state.index.records.find(record=>record.id===state.caseId);}
function elements(role){return {image:el(`${role}Img`),viewer:el(`${role}Viewer`),media:el(`${role}Media`),glb:el(`${role}Glb`)};}
function note(message){el('viewerNote').textContent=message;el('viewerNote').hidden=!message;}
function canRender3d(){try{const canvas=document.createElement('canvas');return Boolean(canvas.getContext('webgl2')||canvas.getContext('webgl'));}catch(_){return false;}}
function setMode(mode){
  state.mode=mode;
  document.body.classList.toggle('orbit-mode',mode==='orbit');
  document.body.classList.toggle('mode-3d',mode==='3d');
  el('orbitControls').hidden=mode!=='orbit';
  el('orbitMode').textContent=mode==='orbit'?'返回图片':'多视角旋转';
  const button=el('viewerMode');
  button.disabled=state.realtimeUnavailable&&mode!=='3d';
  button.textContent=mode==='3d'?'返回图片':state.realtimeUnavailable?'实时 3D 不可用':'实时 3D';
}
function orbitPath(asset){return asset.orbit_grid?.[state.pitch]?.[state.yaw];}
function updateOrbit(){
  const record=currentCase();if(!record)return;
  const grid=record.assets[state.phase].source.orbit_grid;
  state.yaw=((state.yaw%12)+12)%12;
  state.pitch=Math.max(0,Math.min(grid.length-1,state.pitch));
  state.roll=((state.roll%12)+12)%12;
  for(const role of roles){
    const asset=record.assets[state.phase][role];
    const {image}=elements(role);const path=orbitPath(asset)||asset.images[state.view];
    if(image.dataset.path!==path){image.dataset.path=path;image.src=path;}
    image.style.transform=`rotate(${state.roll*30}deg)`;
  }
  el('yawRange').value=state.yaw;el('pitchRange').value=state.pitch;el('rollRange').value=state.roll;
  el('yawCount').textContent=`${state.yaw+1} / 12`;
  el('pitchCount').textContent=`${state.pitch+1} / ${grid.length}`;
  el('rollCount').textContent=`${state.roll*30}°`;
}
function setOrbit(message=''){
  if(state.mode!=='orbit'){
    state.yaw=state.view===0?0:9;state.pitch=state.view===0?2:4;state.roll=0;
  }
  setMode('orbit');render();note(message);
}
function fallback(message){state.realtimeUnavailable=true;setOrbit(message);}
function updateViewer(role,asset){
  if(state.mode!=='3d'||!state.viewerReady)return;
  const {viewer,media}=elements(role);if(viewer.dataset.glb===asset.glb)return;
  clearTimeout(timers.get(role));media.classList.remove('ready');viewer.dataset.glb=asset.glb;
  timers.set(role,setTimeout(()=>{if(state.mode==='3d'&&!media.classList.contains('ready'))fallback('实时 3D 加载超时，已切换到离线多视角。');},15000));
  viewer.src=asset.glb;
}
async function enable3d(){
  if(!canRender3d()){fallback('此浏览器无法创建 WebGL 画面，已切换到离线多视角。');return;}
  setMode('3d');note('正在载入两个可旋转手模型…');
  try{viewerModule ||= import('./vendor/model-viewer.min.js').then(()=>customElements.whenDefined('model-viewer'));await viewerModule;}
  catch(error){console.error(error);fallback('3D 组件加载失败，已切换到离线多视角。');return;}
  if(state.mode!=='3d')return;
  state.viewerReady=true;
  for(const role of roles){elements(role).viewer.setAttribute('camera-orbit',state.view===0?'135deg 70deg auto':'45deg 75deg auto');updateViewer(role,currentCase().assets[state.phase][role]);}
}
function render(){
  const record=currentCase();if(!record)return;
  el('caseTitle').textContent=`${record.category.replaceAll('_',' ')} · ${record.id}`;
  el('sourceName').textContent=record.hand==='shadow'?'Shadow Hand':'Allegro Hand';
  document.querySelectorAll('[data-phase]').forEach(button=>button.classList.toggle('active',button.dataset.phase===state.phase));
  document.querySelectorAll('[data-view]').forEach(button=>button.classList.toggle('active',Number(button.dataset.view)===state.view));
  document.querySelectorAll('.cases button').forEach(button=>button.classList.toggle('active',button.dataset.id===state.caseId));
  for(const role of roles){
    const asset=record.assets[state.phase][role];const {image,glb}=elements(role);
    glb.href=asset.glb;
    if(state.mode!=='orbit'){
      const path=asset.images[state.view];if(image.dataset.path!==path){image.dataset.path=path;image.src=path;}
      image.style.transform='';
    }
    updateViewer(role,asset);
  }
  if(state.mode==='orbit')updateOrbit();
  const errors=record.hand_only_fit.phases[state.phase];
  const values=Object.values(errors);
  const mean=key=>values.reduce((sum,item)=>sum+item[key],0)/values.length;
  el('actionError').textContent=mean('action_error').toFixed(3);
  el('shapeError').textContent=mean('shape_error').toFixed(3);
  const world=Object.values(record.world_tip_error_mm.hand_only_fit[state.phase]);
  el('worldError').textContent=`${(world.reduce((a,b)=>a+b,0)/world.length).toFixed(1)} mm`;
  const solver=record.solver[state.phase];
  el('solverStatus').textContent=solver.success?'已收敛':'达到迭代上限';
  const body=el('fingerErrors');body.replaceChildren();
  for(const [finger,error] of Object.entries(errors)){
    const row=document.createElement('tr');
    for(const value of [FINGERS[finger]||finger,error.action_error.toFixed(3),error.shape_error.toFixed(3)]){
      const cell=document.createElement('td');cell.textContent=value;row.append(cell);
    }
    body.append(row);
  }
  for(const finger of record.unmapped_wuji_fingers){
    const row=document.createElement('tr');for(const value of [FINGERS[finger]||finger,'来源手无对应','—']){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}body.append(row);
  }
  el('sourcePath').textContent=`${record.source} [${record.sample_index}]`;
}
function renderList(){
  const hand=el('handFilter').value,split=el('splitFilter').value;
  const records=state.index.records.filter(record=>(hand==='all'||record.hand===hand)&&(split==='all'||record.split===split));
  if(!records.some(record=>record.id===state.caseId))state.caseId=records[0]?.id;
  const list=el('caseList');list.replaceChildren();
  for(const record of records){
    const button=document.createElement('button');button.type='button';button.dataset.id=record.id;
    button.textContent=record.category.replaceAll('_',' ');
    const small=document.createElement('small');small.textContent=`${record.id} · ${record.split}`;button.append(small);
    button.addEventListener('click',()=>{state.caseId=record.id;render();});list.append(button);
  }
  render();
}
async function start(){
  try{
    const embedded=el('embeddedIndex').textContent.trim();
    if(embedded&&embedded!=='__HAND_ONLY_INDEX_JSON__')state.index=JSON.parse(embedded);
    else{const response=await fetch('index.json');if(!response.ok)throw new Error(`HTTP ${response.status}`);state.index=await response.json();}
    state.caseId=state.index.records.find(record=>record.id==='sh_tripod_obj')?.id||state.index.records[0]?.id;
    if(!state.caseId)throw new Error('索引中没有样本');
    el('handFilter').addEventListener('change',renderList);el('splitFilter').addEventListener('change',renderList);
    document.querySelectorAll('[data-phase]').forEach(button=>button.addEventListener('click',()=>{state.phase=button.dataset.phase;render();}));
    document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{state.view=Number(button.dataset.view);if(state.mode==='orbit'){state.yaw=state.view===0?0:9;state.pitch=state.view===0?2:4;state.roll=0;}if(state.mode==='3d')for(const role of roles)elements(role).viewer.setAttribute('camera-orbit',state.view===0?'135deg 70deg auto':'45deg 75deg auto');render();}));
    el('orbitMode').addEventListener('click',()=>{if(state.mode==='orbit'){setMode('image');note('');render();}else setOrbit();});
    el('viewerMode').addEventListener('click',()=>{if(state.mode==='3d'){setMode('image');note('');render();}else enable3d();});
    for(const [id,key,delta] of [['yawPrevious','yaw',-1],['yawNext','yaw',1],['pitchPrevious','pitch',-1],['pitchNext','pitch',1],['rollPrevious','roll',-1],['rollNext','roll',1]])el(id).addEventListener('click',()=>{if(state.mode!=='orbit')setOrbit();state[key]+=delta;updateOrbit();});
    for(const [id,key] of [['yawRange','yaw'],['pitchRange','pitch'],['rollRange','roll']])el(id).addEventListener('input',event=>{state[key]=Number(event.target.value);updateOrbit();});
    for(const role of roles){
      const {image,viewer,media}=elements(role);let drag=null;image.draggable=false;
      image.addEventListener('pointerdown',event=>{if(state.mode!=='orbit')return;drag={x:event.clientX,y:event.clientY,yaw:state.yaw,pitch:state.pitch};image.setPointerCapture(event.pointerId);});
      image.addEventListener('pointermove',event=>{if(!drag||state.mode!=='orbit'||!image.hasPointerCapture(event.pointerId))return;state.yaw=drag.yaw+Math.round((drag.x-event.clientX)/24);state.pitch=drag.pitch+Math.round((drag.y-event.clientY)/36);updateOrbit();});
      image.addEventListener('pointerup',()=>{drag=null;});image.addEventListener('pointercancel',()=>{drag=null;});
      image.addEventListener('error',()=>{if(state.mode!=='orbit')return;const path=currentCase().assets[state.phase][role].images[state.view];if(image.dataset.path!==path){image.dataset.path=path;image.src=path;}note('部分离线视角缺失，已显示基准角度。');});
      viewer.addEventListener('load',()=>{if(state.mode!=='3d')return;clearTimeout(timers.get(role));media.classList.add('ready');if(roles.every(r=>elements(r).media.classList.contains('ready')))note('');});
      viewer.addEventListener('error',()=>{if(state.mode==='3d')fallback('实时 3D 模型加载失败，已切换到离线多视角。');});
      viewer.addEventListener('camera-change',event=>{if(state.mode!=='3d'||event.detail?.source!=='user-interaction')return;const orbit=viewer.getCameraOrbit();for(const other of roles)if(other!==role)elements(other).viewer.setAttribute('camera-orbit',`${orbit.theta}rad ${orbit.phi}rad auto`);});
    }
    window.addEventListener('keydown',event=>{if(['1','2','3'].includes(event.key)){state.phase=Object.keys(PHASES)[Number(event.key)-1];render();}});
    renderList();if(!canRender3d())fallback('此浏览器无法使用实时 3D，已显示离线多视角；请使用三个滑条旋转。');
  }catch(error){el('caseTitle').textContent=`加载失败：${error.message}`;console.error(error);}
}
start();
