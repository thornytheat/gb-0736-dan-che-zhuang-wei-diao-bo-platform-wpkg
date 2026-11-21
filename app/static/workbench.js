import {$, api, clock, date, notice, post, showError, time} from './view.js';
import * as stages from './stages.js';
import {apiTime, fillDraft, local, newLeg, readDraft} from './dispatch.js';

const anchors = [...document.querySelectorAll('.rail-nav [data-nav]')];
const keys = anchors.map(link => link.dataset.nav);
let current, meta, data, extra, selected, revision = 0;
let draftRun, previewResult, previewedLegs;
let bulletinAsOf = null, bulletinData = null;
let busy = false;

function runId() { return meta.manifest.id; }
function activeId() { return meta.history.find(row => row.active).id; }

function updateMeta() {
  const {manifest, shift} = meta;
  $('shift-name').textContent = shift.name;
  $('shift-range').textContent = `${date(shift.start)} · ${time(shift.start)}–${time(shift.end)}`;
  $('run-short').textContent = runId().slice(0, 12);
  $('footer-state').textContent = runId() === activeId() ? '当前班次' : '历史留档';
  $('footer-meta').textContent = `${manifest.zone} · v${manifest.rule_version} · ${date(manifest.generated_at)} ${clock(manifest.generated_at)}`;
  $('export').href = `/api/runs/${runId()}/evidence.json`;
  $('export').removeAttribute('aria-disabled');
  $('rerun').disabled = runId() !== activeId() || busy;
  for (const button of document.querySelectorAll('#upload-form button')) button.disabled = runId() !== activeId() || busy;
}

function paint() {
  if (!meta || !data) return;
  if (current === 'runs') stages.runs(meta, id => load(id));
  else if (current === 'dispatch') {
    if (draftRun !== runId()) {
      draftRun = runId();
      previewResult = previewedLegs = null;
      fillDraft(data.legs, meta.shift, invalidate);
    }
    stages.dispatch(previewResult || data, meta.shift, Boolean(previewResult));
    $('publish').disabled = !previewedLegs || runId() !== activeId() || busy;
  } else if (current === 'bulletin') {
    bulletinData = data;
    stages.bulletin(data, meta.shift);
    $('bulletin-asof').value = local(data.as_of);
    const live = runId() === activeId() && !busy;
    const confirmed = data.draft.totals.confirmed;
    $('publish-partial').disabled = !confirmed || !live;
    $('publish-all').disabled = confirmed !== data.draft.stations.length || !live;
    $('verify-bulletin').disabled = !data.active;
    $('sample-backfill').disabled = !data.sample_remaining || !live;
    for (const button of document.querySelectorAll('#backfill-form button')) button.disabled = !live;
  } else stages[current](data, meta.shift, extra);
}

async function load(run = selected) {
  const key = location.hash.slice(1);
  current = keys.includes(key) ? key : 'replay';
  const stage = current;
  const token = ++revision;
  selected = run;
  data = null;
  const index = keys.indexOf(current);
  const title = anchors[index].lastChild.textContent.trim();
  $('crumb').textContent = $('stage-title').textContent = title;
  $('stage-label').textContent = `班次流程 · ${index + 1} / ${keys.length}`;
  for (const element of document.querySelectorAll('[data-nav]')) {
    if (element.dataset.nav === current) element.setAttribute('aria-current', 'step');
    else element.removeAttribute('aria-current');
  }
  for (const section of document.querySelectorAll('.stage')) section.hidden = true;
  $('kpis').replaceChildren();
  $('rerun').disabled = true;
  $('export').removeAttribute('href');
  $('export').setAttribute('aria-disabled', 'true');
  notice('正在读取班次…');
  try {
    const runMeta = await api(`/api/runs${run ? `?run=${encodeURIComponent(run)}` : ''}`);
    if (token !== revision) return;
    const suffix = `?run=${encodeURIComponent(runMeta.manifest.id)}`;
    const bulletinQuery = bulletinAsOf ? `?as_of=${encodeURIComponent(bulletinAsOf)}` : '';
    const [payload, slots] = await Promise.all([
      stage === 'runs' ? runMeta : stage === 'bulletin' ? api(`/api/bulletin${bulletinQuery}`) : api(`/api/${stage}${suffix}`),
      stage === 'replay' ? api(`/api/demand${suffix}`) : null,
    ]);
    if (token !== revision) return;
    meta = runMeta;
    data = stage === 'runs' ? runMeta : stage === 'bulletin' ? payload : payload.data;
    extra = slots?.data;
    updateMeta();
    paint();
    $(`stage-${stage}`).hidden = false;
    notice();
  } catch (error) {
    if (token === revision) showError(error, true);
  }
}

async function mutate(action, success) {
  if (busy) return;
  busy = true;
  const token = revision;
  const form = current === 'dispatch' ? $('dispatch-form') : current === 'intake' ? $('upload-form') : current === 'bulletin' ? $('backfill-form') : null;
  if (form) form.inert = true;
  $('rerun').disabled = $('restore').disabled = true;
  notice('正在计算…');
  try {
    const result = await action();
    if (token === revision) await success(result);
  } catch (error) {
    if (token === revision) showError(error);
  } finally {
    if (form) form.inert = false;
    busy = false;
    $('restore').disabled = false;
    if (meta && data) { updateMeta(); paint(); }
  }
}

function invalidate() {
  previewResult = previewedLegs = null;
  notice();
  paint();
}

window.addEventListener('hashchange', () => {
  if (location.hash !== '#main') { stages.clearSlot(); load(); }
});
for (const id of ['intake-filter', 'replay-mode', 'demand-mode', 'inventory-mode']) $(id).addEventListener('change', paint);
$('clear-slot').addEventListener('click', () => { stages.clearSlot(); paint(); });
$('refresh').addEventListener('click', () => { draftRun = null; bulletinAsOf = null; stages.clearSlot(); load(null); });
$('rerun').addEventListener('click', () => mutate(() => post('/api/runs/rerun', {expected: runId()}), async result => {
  draftRun = null;
  await load(null);
  notice(result.created ? '已归档新版本' : '重跑完成 · 沿用同一班次编号');
}));
$('restore').addEventListener('click', () => mutate(() => post('/api/runs/restore', {target: runId(), expected: activeId()}), async () => {
  draftRun = null;
  await load(null);
  notice('已切回所选班次');
}));
$('upload-form').addEventListener('submit', event => {
  event.preventDefault();
  const file = new FormData(event.currentTarget);
  file.set('expected', runId());
  mutate(() => api('/api/intake', {method: 'POST', body: file}), async result => {
    $('upload-form').reset();
    await load(null);
    notice(result.created ? '收件完成 · 已归档' : '文件已收件 · 班次编号保持');
  });
});
$('dispatch-form').addEventListener('input', invalidate);
$('dispatch-form').addEventListener('submit', event => {
  event.preventDefault();
  const legs = readDraft();
  mutate(() => post('/api/dispatch/preview', {run: runId(), legs}), result => {
    previewResult = result.dispatch;
    previewedLegs = legs;
    notice('试算完成');
  });
});
$('publish').addEventListener('click', () => mutate(() => post('/api/dispatch/publish', {expected: runId(), legs: previewedLegs}), async () => {
  draftRun = null;
  await load(null);
  notice('方案已发布');
}));
$('sample-plan').addEventListener('click', () => {
  if (busy) return;
  fillDraft(meta.sample_plan, meta.shift, invalidate);
  invalidate();
});

function publishBulletin(mode) {
  if (!bulletinData) return;
  const expected = bulletinData.active ? bulletinData.active.manifest.id : null;
  mutate(() => post('/api/bulletin/publish', {expected, as_of: bulletinData.as_of, mode}), async result => {
    bulletinAsOf = null;
    await load(null);
    notice(result.created ? `公报已发布 · ${result.id.slice(0, 12)}` : '车况结论不变 · 沿用同一公报编号');
  });
}

$('cutoff-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!$('bulletin-asof').value) return;
  bulletinAsOf = apiTime($('bulletin-asof').value);
  load();
});
$('publish-partial').addEventListener('click', () => publishBulletin('partial'));
$('publish-all').addEventListener('click', () => publishBulletin('all'));
$('verify-bulletin').addEventListener('click', () => {
  const id = bulletinData && bulletinData.active && bulletinData.active.manifest.id;
  if (!id) return;
  mutate(() => post('/api/bulletin/verify', {id}), () => notice('复核一致 · 公报与封存输入重算相符'));
});
$('backfill-form').addEventListener('submit', event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  form.set('covered_until', apiTime(form.get('covered_until')));
  mutate(() => api('/api/bulletin/backfill', {method: 'POST', body: form}), async result => {
    $('backfill-form').reset();
    bulletinAsOf = null;
    await load(null);
    notice(result.created ? `批次已收件 · 采信 ${result.accepted} 笔 · 隔离 ${result.quarantined} 笔` : '批次已存在 · 内容一致未重复入账');
  });
});
$('sample-backfill').addEventListener('click', () => mutate(() => post('/api/bulletin/backfill/sample', {}), async result => {
  bulletinAsOf = null;
  await load(null);
  notice(result.id ? `样例批次 ${result.id} 已收件 · 剩余 ${result.remaining} 批` : '样例批次已全部收件');
}));
$('discard').addEventListener('click', () => {
  fillDraft(data.legs, meta.shift, invalidate);
  invalidate();
  notice('已恢复发布方案');
});
$('add-leg').addEventListener('click', () => {
  if (!$('dispatch-form').reportValidity()) return;
  const legs = readDraft();
  if (legs.length >= 20) { notice('最多 20 趟行程', true); return; }
  fillDraft([...legs, newLeg(legs, meta.shift)], meta.shift, invalidate);
  invalidate();
});
load(null);
