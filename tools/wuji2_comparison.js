const PHASES = {pregrasp:'预抓取', grasp:'抓取', squeeze:'收紧'};
const FINGERS = {thumb:'拇指',index:'食指',middle:'中指',ring:'无名指',pinky:'小指'};
const state = {index:null, caseId:null, phase:'grasp', view:0, mode:'image', viewerReady:false};
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
  const button = el('viewerMode');
  button.textContent = mode === '3d' ? '返回图片' : '开启 3D 旋转';
  button.setAttribute('aria-pressed', String(mode === '3d'));
}
function setOrbit(view) {
  for (const [mode, role] of CARDS) cardElements(mode, role).viewer.setAttribute('camera-orbit', CAMERA_ORBITS[view]);
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
      note('部分模型加载超时，相关格子继续显示静态图。');
    }
  }, 15000));
  viewer.src = asset.glb;
}
async function enable3d() {
  if (!canRender3d()) { note('此浏览器无法创建 WebGL 画面，继续显示静态图。'); return; }
  setMode('3d');
  note('正在载入四个可旋转模型…');
  try {
    viewerModule ||= import('./vendor/model-viewer.min.js').then(() => customElements.whenDefined('model-viewer'));
    await viewerModule;
  } catch (error) {
    setMode('image');
    note('3D 组件加载失败，继续显示静态图。');
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
  image.src = asset.images[state.view];
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
  el('stageHint').textContent = `${PHASES[state.phase]} · ${state.mode === '3d' ? '可拖动旋转 · 滚轮缩放' : state.view === 0 ? '正斜视' : '侧上视'} · 掌心对齐指尖均距 ${meanShapeError.toFixed(1)} mm`;
  for (const mode of ['scene','hand']) for (const role of ['source','wuji']) setCard(mode,role);
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
    document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',()=>{state.view=Number(button.dataset.view);if(state.mode==='3d')setOrbit(state.view);render();}));
    el('viewerMode').addEventListener('click',()=>{if(state.mode==='3d'){setMode('image');note('');render();}else enable3d();});
    for (const [mode, role] of CARDS) {
      const {media, viewer} = cardElements(mode, role);
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
            note('部分模型未能正常渲染，相关格子继续显示静态图。');
          }
          console.error(error);
        }
      });
      viewer.addEventListener('error', () => {
        if (state.mode !== '3d') return;
        clearTimeout(loadTimers.get(viewer));
        media.classList.remove('ready');
        note('部分模型加载失败，相关格子继续显示静态图。');
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
  } catch (error) {
    el('caseTitle').textContent = `加载失败：${error.message}`;
  }
}
start();
