const PHASE_META = {
  pregrasp: { label: '预抓取', english: 'Pre-grasp', description: '手掌接近物体、手指保持开放的准备姿态，用于观察接近方向和初始包络。' },
  grasp: { label: '抓取', english: 'Grasp', description: '手指已经围绕物体形成主要接触，是判断抓取类型和手物关系的核心阶段。' },
  squeeze: { label: '收紧', english: 'Squeeze', description: '在抓取姿态基础上继续闭合手指，用于形成更稳定的接触和约束。' },
};
const state = { data: null, className: null, recordIndex: 0, phase: 'grasp', mode: 'static', orbitYaw: 0, orbitPitch: 0, orbitRoll: 0, playing: false, playTimer: null, loadTimer: null, loadId: 0, modelPath: null };
const el = id => document.getElementById(id);
const viewer = el('viewer');
const poster = el('poster');
const orbitImage = el('orbitImage');
let viewerModule;
let contextLossListenerAdded = false;

function classParts(name) {
  const match = name.match(/^(\d+)_(.*)$/);
  return { number: match ? match[1] : '—', label: (match ? match[2] : name).replaceAll('_', ' ') };
}
function objectName(record) { return record.source.split('/')[1] || record.source; }
function recordsForClass() { return state.data.records.filter(record => record.class_name === state.className); }
function activeRecord() { return recordsForClass()[state.recordIndex]; }
function versioned(path) { return path + '?v=' + encodeURIComponent(state.data.generated_at || '1'); }
function setStatus(kind, label) {
  const status = el('systemStatus');
  status.className = 'status ' + kind;
  status.querySelector('span:last-child').textContent = label;
}
function note(message) {
  el('stageNote').textContent = message;
  el('stageNote').classList.toggle('visible', Boolean(message));
}
function posterPath(record) {
  return record.phases[state.phase].png;
}
function showPoster() {
  const path = posterPath(activeRecord());
  if (poster.getAttribute('data-path') !== path) {
    poster.dataset.path = path;
    poster.src = versioned(path);
  }
  poster.classList.remove('hidden');
}
function invalidateLoad() {
  state.loadId++;
  clearTimeout(state.loadTimer);
  el('loadState').classList.remove('visible');
}
function setStatic(message = '') {
  invalidateLoad();
  state.mode = 'static';
  el('stage').classList.remove('three-d');
  el('stage').classList.remove('orbit');
  el('errorState').classList.remove('visible');
  el('viewerMode').textContent = '切换到 3D';
  el('viewerHint').textContent = '拖动旋转 · 滚轮缩放 · 双击聚焦';
  showPoster();
  note(message);
  setStatus('ready', '静态预览可用');
}
function orbitGrid() {
  const phase = activeRecord().phases[state.phase];
  return phase.orbit_grid || (phase.orbit?.length ? [phase.orbit] : []);
}
function updateOrbitImage() {
  const grid = orbitGrid();
  if (!grid.length) return;
  state.orbitPitch = Math.max(0, Math.min(grid.length - 1, state.orbitPitch));
  const frames = grid[state.orbitPitch];
  state.orbitYaw = (state.orbitYaw % frames.length + frames.length) % frames.length;
  state.orbitRoll = (state.orbitRoll % 12 + 12) % 12;
  const path = frames[state.orbitYaw];
  if (orbitImage.dataset.path !== path) {
    orbitImage.dataset.path = path;
    orbitImage.src = versioned(path);
  }
  orbitImage.style.transform = `rotate(${state.orbitRoll * 30}deg)`;
  el('yawCount').textContent = (state.orbitYaw + 1) + ' / ' + frames.length;
  el('pitchCount').textContent = (state.orbitPitch + 1) + ' / ' + grid.length;
  el('rollCount').textContent = state.orbitRoll * 30 + '°';
}
function setOrbit(message = '') {
  const grid = orbitGrid();
  if (!grid.length) {
    setStatic(message || '此样本没有多视角画面；可下载当前 GLB 用三维查看器打开。');
    return;
  }
  const keepView = state.mode === 'orbit';
  invalidateLoad();
  state.mode = 'orbit';
  if (!keepView) {
    state.orbitYaw = 0;
    state.orbitPitch = Math.floor(grid.length / 2);
    state.orbitRoll = 0;
  }
  el('stage').classList.remove('three-d');
  el('stage').classList.add('orbit');
  el('errorState').classList.remove('visible');
  el('viewerMode').textContent = '切换到静态';
  el('viewerHint').textContent = '预渲染多视角 · 三组箭头控制水平、俯仰和滚转';
  showPoster();
  updateOrbitImage();
  note(message || '预渲染多视角：拖动调整水平与俯仰，三组箭头分别控制三个方向。');
  setStatus('ready', '多视角预览可用');
}
function show3dReady() {
  invalidateLoad();
  poster.classList.add('hidden');
  el('stage').classList.add('three-d');
  el('stage').classList.remove('orbit');
  el('viewerHint').textContent = '拖动旋转 · 滚轮缩放 · 双击聚焦';
  note('');
  setStatus('ready', '三维模型已就绪');
}
function ensureViewer() {
  if (!viewerModule) {
    viewerModule = import('./vendor/model-viewer.min.js')
      .then(() => customElements.whenDefined('model-viewer'));
  }
  return viewerModule;
}
function canRender3d() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch (_) {
    return false;
  }
}
async function validateLoadedModel(id) {
  try {
    await verify3dFrame();
  } catch (error) {
    if (id === state.loadId && state.mode === '3d') {
      setOrbit('实时 3D 渲染失败，已切换到预渲染多视角；拖动画面旋转。');
    }
    console.error(error);
    return;
  }
  if (id === state.loadId && state.mode === '3d') show3dReady();
}
async function verify3dFrame() {
  if (typeof viewer.toBlob !== 'function' || typeof createImageBitmap !== 'function') {
    throw new Error('3D frame capture is unavailable');
  }
  let lastError;
  for (let attempt = 0; attempt < 4; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 350));
    try {
      const blob = await Promise.race([
        viewer.toBlob({ mimeType: 'image/png' }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('3D frame capture timed out')), 3000)),
      ]);
      const bitmap = await createImageBitmap(blob);
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 64;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(bitmap, 0, 0, 64, 64);
      bitmap.close?.();
      const pixels = context.getImageData(0, 0, 64, 64).data;
      let bluePixels = 0;
      for (let i = 0; i < pixels.length; i += 4) {
        if (pixels[i + 2] > pixels[i] + 25 && pixels[i + 2] > pixels[i + 1] + 8 && pixels[i + 2] > 100) bluePixels++;
      }
      if (bluePixels >= 10) return;
      lastError = new Error('3D frame does not contain the hand');
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}
async function loadModel() {
  const record = activeRecord();
  const path = record.phases[state.phase].glb;
  invalidateLoad();
  const id = state.loadId;
  state.mode = '3d';
  el('stage').classList.remove('three-d');
  el('stage').classList.remove('orbit');
  showPoster();
  note('');
  el('errorState').classList.remove('visible');
  el('viewerMode').textContent = '切换到静态';
  el('loadDetail').textContent = PHASE_META[state.phase].label + ' · ' + path.split('/').pop();
  setStatus('ready', '静态预览可用 · 正在载入 3D');
  if (!canRender3d()) {
    setOrbit('此浏览器无法创建 WebGL 画面；已切换到预渲染多视角，拖动画面旋转。');
    return;
  }
  try {
    await ensureViewer();
  } catch (error) {
    if (id === state.loadId) setOrbit('3D 组件不可用，已切换到预渲染多视角。');
    console.error(error);
    return;
  }
  if (id !== state.loadId || state.mode !== '3d') return;
  if (!contextLossListenerAdded) {
    const canvas = viewer.shadowRoot?.querySelector('canvas');
    if (canvas) {
      canvas.addEventListener('webglcontextlost', () => {
        if (state.mode === '3d') setOrbit('浏览器的 3D 上下文已中断，已切换到预渲染多视角。');
      });
      contextLossListenerAdded = true;
    }
  }
  if (viewer.loaded && state.modelPath === path) {
    validateLoadedModel(id);
    return;
  }
  state.modelPath = path;
  state.loadTimer = setTimeout(() => {
    if (id === state.loadId && state.mode === '3d') {
      setOrbit('3D 加载超时，已切换到预渲染多视角。');
    }
  }, 20000);
  viewer.src = versioned(path);
}
function renderClasses() {
  const counts = new Map();
  state.data.records.forEach(record => counts.set(record.class_name, (counts.get(record.class_name) || 0) + 1));
  const nodes = state.data.classes.filter(name => counts.has(name)).map(name => {
    const parts = classParts(name);
    const button = document.createElement('button');
    button.className = 'class-button' + (name === state.className ? ' active' : '');
    button.innerHTML = '<span class="class-number"></span><span class="class-name"></span><span class="class-count"></span>';
    button.querySelector('.class-number').textContent = parts.number;
    button.querySelector('.class-name').textContent = parts.label;
    button.querySelector('.class-count').textContent = counts.get(name);
    button.onclick = () => { state.className = name; state.recordIndex = 0; stopPlayback(); renderAll(); };
    return button;
  });
  el('classList').replaceChildren(...nodes);
}
function renderSamples() {
  const records = recordsForClass();
  el('sampleCount').textContent = records.length + ' 个';
  const nodes = records.map((record, index) => {
    const button = document.createElement('button');
    button.className = 'sample-button' + (index === state.recordIndex ? ' active' : '');
    button.innerHTML = '<div class="sample-label"></div><div class="sample-object"></div>';
    button.querySelector('.sample-label').textContent = '样本 ' + String(record.sample_number).padStart(2, '0');
    button.querySelector('.sample-object').textContent = objectName(record);
    button.onclick = () => { state.recordIndex = index; stopPlayback(); renderSamples(); renderRecord(); };
    return button;
  });
  el('sampleList').replaceChildren(...nodes);
}
function renderPhases() {
  const nodes = state.data.phases.map((phase, index) => {
    const button = document.createElement('button');
    button.className = 'phase-button' + (phase === state.phase ? ' active' : '');
    button.innerHTML = '<span></span><small></small>';
    button.querySelector('span').textContent = PHASE_META[phase].label;
    button.querySelector('small').textContent = (index + 1) + ' · ' + PHASE_META[phase].english;
    button.onclick = () => selectPhase(phase);
    return button;
  });
  const play = document.createElement('button');
  play.className = 'play-button';
  play.title = state.playing ? '暂停阶段播放' : '自动播放三个阶段';
  play.textContent = state.playing ? 'Ⅱ' : '▶';
  play.onclick = togglePlayback;
  el('phaseBar').replaceChildren(...nodes, play);
}
function renderRecord() {
  const record = activeRecord();
  const parts = classParts(record.class_name);
  el('viewerKicker').textContent = 'Class ' + parts.number + ' · Sample ' + String(record.sample_number).padStart(2, '0');
  el('viewerHeading').textContent = parts.label;
  el('classBadge').textContent = 'CLASS ' + parts.number;
  el('infoTitle').textContent = parts.label;
  el('infoSubtitle').textContent = '代表样本 ' + record.sample_number + ' · ' + objectName(record);
  el('sampleIndex').textContent = record.sample_index;
  el('sampleTotal').textContent = record.sample_count_in_file;
  el('sourcePath').textContent = record.source;
  const download = el('downloadModel');
  download.href = versioned(record.phases[state.phase].glb);
  download.download = record.class_name + '_sample_' + String(record.sample_number).padStart(2, '0') + '_' + state.phase + '.glb';
  el('phaseDescription').textContent = PHASE_META[state.phase].description;
  renderPhases();
  if (state.mode === '3d') loadModel(); else if (state.mode === 'orbit') setOrbit(); else setStatic();
}
function renderAll() { renderClasses(); renderSamples(); renderRecord(); }
function selectPhase(phase) {
  if (!PHASE_META[phase] || phase === state.phase) return;
  state.phase = phase;
  renderRecord();
}
function stopPlayback() {
  state.playing = false;
  clearInterval(state.playTimer);
  state.playTimer = null;
  if (state.data) renderPhases();
}
function togglePlayback() {
  if (state.playing) { stopPlayback(); return; }
  state.playing = true;
  renderPhases();
  state.playTimer = setInterval(() => {
    const phases = state.data.phases;
    selectPhase(phases[(phases.indexOf(state.phase) + 1) % phases.length]);
  }, 2400);
}
function moveSample(delta) {
  const records = recordsForClass();
  state.recordIndex = (state.recordIndex + delta + records.length) % records.length;
  stopPlayback();
  renderSamples();
  renderRecord();
}
function resetCamera() {
  if (state.mode === 'orbit') {
    state.orbitYaw = 0;
    state.orbitPitch = Math.floor(orbitGrid().length / 2);
    state.orbitRoll = 0;
    updateOrbitImage();
    return;
  }
  viewer.cameraOrbit = '135deg 70deg auto';
  viewer.cameraTarget = 'auto auto auto';
  viewer.fieldOfView = '30deg';
  viewer.jumpCameraToGoal?.();
}

viewer.addEventListener('load', () => {
  if (state.mode !== '3d' || !viewer.loaded) return;
  validateLoadedModel(state.loadId);
});
viewer.addEventListener('error', event => {
  if (state.mode === '3d') setOrbit('3D 在当前浏览器中加载失败，已切换到预渲染多视角。');
  console.error(event);
});
poster.addEventListener('error', () => {
  if (state.mode === 'static') {
    note('静态图片加载失败，请检查 previews 目录或重新导出。');
    setStatus('error', '静态图片不可用');
  }
});
orbitImage.addEventListener('error', () => {
  if (state.mode === 'orbit') setStatic('多视角图片加载失败，已返回静态画面。');
});
el('viewerMode').onclick = () => state.mode === 'static' ? loadModel() : setStatic();
el('yawPrevious').onclick = () => { state.orbitYaw--; updateOrbitImage(); };
el('yawNext').onclick = () => { state.orbitYaw++; updateOrbitImage(); };
el('pitchPrevious').onclick = () => { state.orbitPitch--; updateOrbitImage(); };
el('pitchNext').onclick = () => { state.orbitPitch++; updateOrbitImage(); };
el('rollPrevious').onclick = () => { state.orbitRoll--; updateOrbitImage(); };
el('rollNext').onclick = () => { state.orbitRoll++; updateOrbitImage(); };
let orbitDrag = null;
orbitImage.addEventListener('pointerdown', event => {
  if (state.mode !== 'orbit') return;
  orbitDrag = { x: event.clientX, y: event.clientY, yaw: state.orbitYaw, pitch: state.orbitPitch };
  orbitImage.setPointerCapture(event.pointerId);
});
orbitImage.addEventListener('pointermove', event => {
  if (!orbitDrag || state.mode !== 'orbit') return;
  state.orbitYaw = orbitDrag.yaw + Math.round((orbitDrag.x - event.clientX) / 24);
  state.orbitPitch = orbitDrag.pitch + Math.round((orbitDrag.y - event.clientY) / 36);
  updateOrbitImage();
});
orbitImage.addEventListener('pointerup', () => { orbitDrag = null; });
orbitImage.addEventListener('pointercancel', () => { orbitDrag = null; });
el('retryButton').onclick = () => loadModel();
el('resetCamera').onclick = resetCamera;
el('fullscreenButton').onclick = () => document.fullscreenElement ? document.exitFullscreen() : el('stage').requestFullscreen();
el('helpButton').onclick = () => el('shortcutSection').scrollIntoView({ behavior: 'smooth', block: 'center' });
document.addEventListener('keydown', event => {
  if (!state.data) return;
  if (event.key >= '1' && event.key <= '3') selectPhase(state.data.phases[Number(event.key) - 1]);
  else if (event.key === 'ArrowLeft') moveSample(-1);
  else if (event.key === 'ArrowRight') moveSample(1);
  else if (event.key.toLowerCase() === 'r') resetCamera();
  else if (event.key.toLowerCase() === 'f') el('fullscreenButton').click();
});

fetch('index.json', { cache: 'no-store' })
  .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
  .then(data => {
    if (!data.records?.length) throw new Error('index.json 中没有可视化记录');
    if (!data.records.every(record => data.phases.every(phase => record.phases[phase]?.png && record.phases[phase]?.glb))) {
      throw new Error('图鉴索引缺少阶段图片或 3D 模型，请重新运行导出器');
    }
    state.data = data;
    state.className = data.classes.find(name => data.records.some(record => record.class_name === name)) || data.records[0].class_name;
    renderAll();
  })
  .catch(error => {
    el('loadState').classList.remove('visible');
    el('errorDetail').textContent = '索引载入失败：' + error.message + '。请使用 HTTP 服务打开页面。';
    el('errorState').classList.add('visible');
    setStatus('error', '数据索引不可用');
  });
