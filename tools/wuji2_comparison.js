const PHASES = {pregrasp:'预抓取', grasp:'抓取', squeeze:'收紧'};
const FINGERS = {thumb:'拇指',index:'食指',middle:'中指',ring:'无名指',pinky:'小指'};
const state = {index:null, caseId:null, phase:'grasp', view:0};
const el = id => document.getElementById(id);

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
  const prefix = mode === 'scene' ? 'scene' : 'hand';
  const suffix = role === 'source' ? 'Source' : 'Wuji';
  el(`${prefix}${suffix}Img`).src = asset.images[state.view];
  el(`${prefix}${suffix}Glb`).href = asset.glb;
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
  el('stageHint').textContent = `${PHASES[state.phase]} · ${state.view === 0 ? '正斜视' : '侧上视'} · 掌心对齐指尖均距 ${meanShapeError.toFixed(1)} mm`;
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
    const response = await fetch('index.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.index = await response.json();
    state.caseId = state.index.records[0]?.id;
    if (!state.caseId) throw new Error('索引中没有样本');
    el('handFilter').addEventListener('change',renderList);
    el('splitFilter').addEventListener('change',renderList);
    document.querySelectorAll('[data-phase]').forEach(button => button.addEventListener('click',()=>{state.phase=button.dataset.phase;render();}));
    document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',()=>{state.view=Number(button.dataset.view);render();}));
    window.addEventListener('keydown',event=>{if (['1','2','3'].includes(event.key)) {state.phase=Object.keys(PHASES)[Number(event.key)-1];render();}});
    renderList();
  } catch (error) {
    el('caseTitle').textContent = `加载失败：${error.message}`;
  }
}
start();
