const PHASES = {pregrasp:'预抓取', grasp:'抓取', squeeze:'收紧'};
const FINGERS = {thumb:'拇指',index:'食指',middle:'中指',ring:'无名指',pinky:'小指'};
const state = {index:null, caseId:null, phase:'grasp', view:0, mode:'image', viewerReady:false,
               orbitYaw:0, orbitPitch:2, orbitRoll:0, realtimeUnavailable:false};
const el = id => document.getElementById(id);
const CARDS = [['scene','source'],['scene','wuji'],['hand','source'],['hand','wuji']];
const CAMERA_ORBITS = ['135deg 70deg auto','45deg 75deg auto'];
let viewerModule;
const loadTimers = new Map();

function cardElements(mode, role) {
  const prefix = mode === 'scene' ? 'scene' : 'hand';
  const suffix = role === 'source' ? 'Source' : 'Wuji';
  return {media:el(`${prefix}${suffix}Media`), image:el(`${prefix}${suffix}Img`),
          viewer:el(`${prefix}${suffix}Viewer`), download:el(`${prefix}${suffix}Glb`)};
}
function note(message) {
  el('viewerNote').textContent = message;
  el('viewerNote').hidden = !message;
}
function canRender3d() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch (_) { return false; }
}
function setMode(mode) {
  state.mode = mode;
  document.body.classList.toggle('is-3d', mode === '3d');
  document.body.classList.toggle('is-orbit', mode === 'orbit');
  el('orbitControls').hidden = mode !== 'orbit';
  const realtimeButton = el('viewerMode');
  realtimeButton.disabled = state.realtimeUnavailable && mode !== '3d';
  realtimeButton.textContent = mode === '3d' ? '返回图片' : state.realtimeUnavailable ? '实时 3D 不可用' : '实时 3D';
  realtimeButton.title = state.realtimeUnavailable ? '当前浏览器无法显示实时 3D，请使用下面的三个视角滑条' : '加载可交互的 GLB 模型';
  realtimeButton.setAttribute('aria-pressed', String(mode === '3d'));
  el('orbitMode').textContent = mode === 'orbit' ? '返回图片' : '多视角旋转';
  el('orbitMode').setAttribute('aria-pressed', String(mode === 'orbit'));
}
function setOrbit(view) {
  for (const [mode, role] of CARDS) cardElements(mode, role).viewer.setAttribute('camera-orbit', CAMERA_ORBITS[view]);
}
function orbitGrid() { return currentCase()?.assets[state.phase].scene.source.orbit_grid; }
function orbitPath(asset) { return asset.orbit_grid?.[state.orbitPitch]?.[state.orbitYaw]; }
function orbitTransform() {
  return `rotate(${state.orbitRoll * 30}deg)`;
}
function updateOrbitFrames() {
  const grid = orbitGrid();
  if (!grid?.length) return;
  state.orbitPitch = Math.max(0, Math.min(grid.length - 1, state.orbitPitch));
  state.orbitYaw = ((state.orbitYaw % grid[0].length) + grid[0].length) % grid[0].length;
  state.orbitRoll = ((state.orbitRoll % 12) + 12) % 12;
  for (const [mode, role] of CARDS) {
    const asset = currentCase().assets[state.phase][mode][role];
    const {image} = cardElements(mode, role);
    const path = orbitPath(asset) || asset.images[state.view];
    if (image.dataset.path !== path) {image.dataset.path = path;image.src = path;}
    image.style.transform = orbitTransform();
  }
  el('yawCount').textContent = `${state.orbitYaw + 1} / ${grid[0].length}`;
  el('pitchCount').textContent = `${state.orbitPitch + 1} / ${grid.length}`;
  el('rollCount').textContent = `${state.orbitRoll * 30}°`;
  el('yawRange').value = state.orbitYaw;
  el('pitchRange').value = state.orbitPitch;
  el('rollRange').value = state.orbitRoll;
}
function setOrbitMode(message = '') {
  if (!orbitGrid()?.length) {setMode('image');note('此样本尚无多视角图片，请重新导出。');return;}
  const alreadyOrbit = state.mode === 'orbit';
  if (!alreadyOrbit) {
    state.orbitYaw = state.view === 0 ? 0 : 9;
    state.orbitPitch = state.view === 0 ? 2 : 4;
    state.orbitRoll = 0;
  }
  setMode('orbit');
  render();
  note(message || '离线多视角：使用水平、俯仰、滚转三个滑条，或拖动任一画面同步调整四格。');
}
function fallbackFrom3d(message) {
  state.realtimeUnavailable = true;
  setOrbitMode(message);
}
async function verifyFrame(viewer, role) {
  if (typeof viewer.toBlob !== 'function' || typeof createImageBitmap !== 'function') throw new Error('无法检查 3D 画面');
  for (let attempt = 0; attempt < 4; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 300));
    const blob = await Promise.race([
      viewer.toBlob({mimeType:'image/png'}),
      new Promise((_, reject) => setTimeout(() => reject(new Error('3D 画面检查超时')), 3000)),
    ]);
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64;
    const context = canvas.getContext('2d', {willReadFrequently:true});
    context.drawImage(bitmap, 0, 0, 64, 64);
    bitmap.close?.();
    const pixels = context.getImageData(0, 0, 64, 64).data;
    let handPixels = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (role === 'source' ? pixels[i+2] > pixels[i] + 20 && pixels[i+2] > pixels[i+1] + 8 && pixels[i+2] > 80
                            : pixels[i+1] > pixels[i] + 10 && pixels[i+1] > pixels[i+2] + 2 && pixels[i+1] > 55) handPixels++;
    }
    if (handPixels >= 8) return;
  }
  throw new Error('3D 画面未显示手部');
}
function updateViewer(mode, role, asset) {
  const {media, viewer} = cardElements(mode, role);
  if (state.mode !== '3d' || !state.viewerReady) return;
  if (viewer.dataset.glb === asset.glb) return;
  media.classList.remove('ready');
  clearTimeout(loadTimers.get(viewer));
  viewer.dataset.glb = asset.glb;
  loadTimers.set(viewer, setTimeout(() => {
    if (state.mode === '3d' && viewer.dataset.glb === asset.glb && !media.classList.contains('ready')) {
      fallbackFrom3d('实时 3D 加载超时，已切换到离线多视角。');
    }
  }, 15000));
  viewer.src = asset.glb;
}
async function enable3d() {
  if (!canRender3d()) { fallbackFrom3d('此浏览器无法创建 WebGL 画面，已切换到离线多视角。'); return; }
  setMode('3d');
  note('正在载入四个可旋转模型…');
  try {
    viewerModule ||= import('./vendor/model-viewer.min.js').then(() => customElements.whenDefined('model-viewer'));
    await viewerModule;
  } catch (error) {
    fallbackFrom3d('3D 组件加载失败，已切换到离线多视角。');
    console.error(error);
    return;
  }
  if (state.mode !== '3d') return;
  state.viewerReady = true;
  setOrbit(state.view);
  for (const [mode, role] of CARDS) updateViewer(mode, role, currentCase().assets[state.phase][mode][role]);
}

function currentCase() { return state.index.records.find(record => record.id === state.caseId); }
function penetration(contact) {
  if (!contact.hand_object_count && !contact.self_count) return '未见接触';
  const distance = contact.min_hand_object_distance_m;
  return distance === null ? '未见接触' : `${Math.max(0,-distance*1000).toFixed(1)} mm`;
}
function selfPenetration(contact) {
  const distance = contact.min_self_distance_m;
  return distance === null ? '未见接触' : `${Math.max(0,-distance*1000).toFixed(1)} mm`;
}
function setCard(mode, role) {
  const record = currentCase();
  const asset = record.assets[state.phase][mode][role];
  const {image, download} = cardElements(mode, role);
  if (state.mode !== 'orbit') {
    const path = asset.images[state.view];
    if (image.dataset.path !== path) {image.dataset.path = path;image.src = path;}
    image.style.transform = '';
  }
  download.href = asset.glb;
  updateViewer(mode, role, asset);
}
function render() {
  const record = currentCase();
  if (!record) return;
  document.querySelectorAll('[data-phase]').forEach(button => button.classList.toggle('active',button.dataset.phase === state.phase));
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active',Number(button.dataset.view) === state.view));
  document.querySelectorAll('.sourceName').forEach(node => node.textContent = record.hand === 'shadow' ? 'Shadow Hand' : 'Allegro Hand');
  el('caseTag').textContent = `${record.split === 'dev' ? '开发集' : '保留集'} · ${record.family.toUpperCase()} · ${record.hand.toUpperCase()}`;
  el('caseTitle').textContent = `${record.category.replaceAll('_',' ')} · ${record.id}`;
  const shapeErrors = Object.values(record.hand_shape_finger_error_mm[state.phase]);
  const meanShapeError = shapeErrors.reduce((sum,value)=>sum+value,0) / shapeErrors.length;
  const viewLabel = state.mode === '3d' ? '实时 3D' : state.mode === 'orbit' ? '离线多视角' : state.view === 0 ? '正斜视' : '侧上视';
  el('stageHint').textContent = `${PHASES[state.phase]} · ${viewLabel} · 掌心对齐指尖均距 ${meanShapeError.toFixed(1)} mm`;
  for (const mode of ['scene','hand']) for (const role of ['source','wuji']) setCard(mode,role);
  if (state.mode === 'orbit') updateOrbitFrames();
  const stats = record.phase_stats[state.phase];
  el('sourcePen').textContent = penetration(stats.source_contact);
  el('wujiPen').textContent = penetration(stats.wuji_contact);
  el('selfPen').textContent = selfPenetration(stats.wuji_contact);
  el('evalStatus').textContent = record.evaluation.passed === true ? '通过' : record.evaluation.passed === false ? '未通过' : '未评估';
  el('evalStatus').className = record.evaluation.passed === true ? 'good' : 'bad';
  const body = el('fingerErrors');
  body.replaceChildren();
  for (const [finger,error] of Object.entries(stats.finger_error_mm)) {
    const row = document.createElement('tr');
    const name = document.createElement('td'); name.textContent = FINGERS[finger] || finger;
    const value = document.createElement('td'); value.textContent = `${error.toFixed(2)} mm`;
    const shape = document.createElement('td'); shape.textContent = `${record.hand_shape_finger_error_mm[state.phase][finger].toFixed(2)} mm`;
    row.append(name,value,shape); body.append(row);
  }
  if (record.hand === 'allegro') {
    const row = document.createElement('tr');
    const name = document.createElement('td'); name.textContent = '小指';
    const value = document.createElement('td'); value.textContent = '来源手无对应手指';
    const shape = document.createElement('td'); shape.textContent = '—';
    row.append(name,value,shape); body.append(row);
  }
  el('sourcePath').textContent = `${record.source} [${record.sample_index}] · scene_scale ${record.scene_scale.toFixed(3)}`;
  document.querySelectorAll('.case').forEach(button => button.classList.toggle('active',button.dataset.id === state.caseId));
}
function renderList() {
  const hand = el('handFilter').value;
  const split = el('splitFilter').value;
  const list = el('caseList'); list.replaceChildren();
  const records = state.index.records.filter(record => (hand === 'all' || record.hand === hand) && (split === 'all' || record.split === split));
  if (!records.some(record => record.id === state.caseId)) state.caseId = records[0]?.id;
  for (const record of records) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'case'; button.dataset.id = record.id;
    const title = document.createElement('strong'); title.textContent = record.category.replaceAll('_',' ');
    const subtitle = document.createElement('small'); subtitle.textContent = `${record.id} · ${record.family} · ${record.split}`;
    button.append(title,subtitle); button.addEventListener('click',()=>{state.caseId=record.id;render();}); list.append(button);
  }
  render();
}
async function start() {
  try {
    // The older 8767 service serves this directory as its root. In that
    // layout the sibling viewer lives on the shared output service at 8768.
    if (!location.pathname.includes('/wuji2_comparison/')) {
      el('handOnlyLink').href = `${location.protocol}//${location.hostname}:8768/wuji2_hand_only_viewer/`;
    }
    const embeddedIndex = el('embeddedIndex')?.textContent.trim();
    if (embeddedIndex && embeddedIndex !== '__WUJI2_INDEX_JSON__') {
      state.index = JSON.parse(embeddedIndex);
    } else {
      const response = await fetch('index.json');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.index = await response.json();
    }
    state.caseId = state.index.records[0]?.id;
    if (!state.caseId) throw new Error('索引中没有样本');
    el('handFilter').addEventListener('change',renderList);
    el('splitFilter').addEventListener('change',renderList);
    document.querySelectorAll('[data-phase]').forEach(button => button.addEventListener('click',()=>{state.phase=button.dataset.phase;render();}));
    document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',()=>{
      state.view = Number(button.dataset.view);
      if (state.mode === '3d') setOrbit(state.view);
      if (state.mode === 'orbit') {
        state.orbitYaw = state.view === 0 ? 0 : 9;
        state.orbitPitch = state.view === 0 ? 2 : 4;
        state.orbitRoll = 0;
      }
      render();
    }));
    el('viewerMode').addEventListener('click',()=>{if(state.mode==='3d'){setMode('image');note('');render();}else enable3d();});
    el('orbitMode').addEventListener('click',()=>{if(state.mode==='orbit'){setMode('image');note('');render();}else setOrbitMode();});
    const moveOrbit = (axis, delta) => {
      if (state.mode !== 'orbit') setOrbitMode();
      if (state.mode !== 'orbit') return;
      state[axis] += delta;
      updateOrbitFrames();
    };
    for (const [id, axis, delta] of [['yawPrevious','orbitYaw',-1],['yawNext','orbitYaw',1],
                                    ['pitchPrevious','orbitPitch',-1],['pitchNext','orbitPitch',1],
                                    ['rollPrevious','orbitRoll',-1],['rollNext','orbitRoll',1]]) {
      el(id).addEventListener('click',()=>moveOrbit(axis,delta));
    }
    for (const [id, axis] of [['yawRange','orbitYaw'],['pitchRange','orbitPitch'],['rollRange','orbitRoll']]) {
      el(id).addEventListener('input',event=>{state[axis]=Number(event.target.value);updateOrbitFrames();});
    }
    el('resetOrbit').addEventListener('click',()=>{
      state.orbitYaw=0;state.orbitPitch=2;state.orbitRoll=0;updateOrbitFrames();
    });
    let orbitDrag = null;
    for (const [mode, role] of CARDS) {
      const {media, image, viewer} = cardElements(mode, role);
      image.draggable = false;
      image.addEventListener('pointerdown', event => {
        if (state.mode !== 'orbit') return;
        orbitDrag = {x:event.clientX, y:event.clientY, yaw:state.orbitYaw, pitch:state.orbitPitch};
        image.setPointerCapture(event.pointerId);
      });
      image.addEventListener('pointermove', event => {
        if (!orbitDrag || state.mode !== 'orbit' || !image.hasPointerCapture(event.pointerId)) return;
        state.orbitYaw = orbitDrag.yaw + Math.round((orbitDrag.x - event.clientX) / 24);
        state.orbitPitch = orbitDrag.pitch + Math.round((orbitDrag.y - event.clientY) / 36);
        updateOrbitFrames();
      });
      image.addEventListener('pointerup',()=>{orbitDrag=null;});
      image.addEventListener('pointercancel',()=>{orbitDrag=null;});
      image.addEventListener('error',()=>{
        if (state.mode !== 'orbit') return;
        const asset = currentCase().assets[state.phase][mode][role];
        const fallback = asset.images[state.view];
        if (image.dataset.path !== fallback) {image.dataset.path=fallback;image.src=fallback;}
        note('部分多视角画面加载失败，相关格子显示基准角度。');
      });
      viewer.addEventListener('load', async () => {
        const path = viewer.dataset.glb;
        try {
          await verifyFrame(viewer, role);
          if (viewer.dataset.glb !== path) return;
          clearTimeout(loadTimers.get(viewer));
          media.classList.add('ready');
          if (state.mode === '3d' && CARDS.every(([m,r]) => cardElements(m,r).media.classList.contains('ready'))) note('');
        } catch (error) {
          if (state.mode === '3d' && viewer.dataset.glb === path) {
            clearTimeout(loadTimers.get(viewer));
            fallbackFrom3d('实时 3D 画面未能正常渲染，已切换到离线多视角。');
          }
          console.error(error);
        }
      });
      viewer.addEventListener('error', () => {
        if (state.mode !== '3d') return;
        clearTimeout(loadTimers.get(viewer));
        media.classList.remove('ready');
        fallbackFrom3d('实时 3D 模型加载失败，已切换到离线多视角。');
      });
      viewer.addEventListener('camera-change', event => {
        if (state.mode !== '3d' || event.detail?.source !== 'user-interaction') return;
        const orbit = viewer.getCameraOrbit();
        for (const [m,r] of CARDS) {
          const other = cardElements(m,r).viewer;
          if (other !== viewer) other.setAttribute('camera-orbit', `${orbit.theta}rad ${orbit.phi}rad auto`);
        }
      });
    }
    window.addEventListener('keydown',event=>{if (['1','2','3'].includes(event.key)) {state.phase=Object.keys(PHASES)[Number(event.key)-1];render();}});
    renderList();
    if (!canRender3d()) fallbackFrom3d('此浏览器无法创建 WebGL 画面，现已显示离线多视角；请用三个滑条或拖动画面旋转。');
  } catch (error) {
    el('caseTitle').textContent = `加载失败：${error.message}`;
  }
}
start();
