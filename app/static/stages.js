import {$, clock, date, kind, kpis, label, node, outcome, signed, table, time} from './view.js';

const lineRows = rows => rows.map(row => [row.line, row.code, label(row.code), row.raw.join(' ｜ ')]);
const lineHeaders = ['源行', '原因码', '判定', '原始字段'];
const names = shift => id => `${shift.stations[id]?.name || id} · ${id}`;
let selectedSlot = null;
export function clearSlot() { selectedSlot = null; }

export function intake(data, shift) {
  const station = names(shift);
  kpis([['收件', data.input_rows, '行'], ['采信', data.events.length, '行'], ['隔离', data.excluded.length, '行', 'warn'],
    ['迟报', data.late, '笔'], ['文件编码', data.encoding]]);
  const filter = $('intake-filter').value;
  if (filter === 'excluded') table('intake-rows', lineHeaders, lineRows(data.excluded), '没有隔离行');
  else {
    const rows = data.events.filter(row => filter !== 'late' || row.late).map(row =>
      [row.line, row.id, station(row.station), kind(row.kind), clock(row.at), clock(row.received_at), row.note || '—']);
    table('intake-rows', ['源行', '编号', '站点', '租还', '发生', '收件', '备注'], rows, '没有迟报行');
  }
}

export function capacity(data, shift) {
  const station = names(shift);
  kpis([['容量收件', data.input_rows, '行'], ['采信版本', data.accepted, '行'], ['生效区间', data.segments.length, '段'],
    ['容量隔离', data.excluded.length, '行', 'warn'], ['关站区间', data.segments.filter(row => row.slots === 0).length, '段']]);
  table('capacity-rows', ['站点', '开始', '结束', '修订号', '容量（桩）', '源行', '备注'], data.segments.map(row =>
    [station(row.station), time(row.start), time(row.end), row.revision, row.slots, row.line, row.note]));
  table('capacity-errors', lineHeaders, lineRows(data.excluded), '容量记录无冲突');
}

function tide(data, shift, onSlot) {
  const chart = $('tidal-chart');
  const codes = Object.keys(shift.stations);
  const columns = data.slots.filter(row => row.station === codes[0]);
  chart.style.setProperty('--slots', columns.length);
  const grid = [node('span', '站点 / 时段', 'subtle'), ...columns.map(row => node('span', time(row.at), 'tidal-time'))];
  for (const code of codes) {
    grid.push(node('span', shift.stations[code].name, 'tidal-station'));
    for (const slot of data.slots.filter(row => row.station === code)) {
      const misses = slot.missed_rent + slot.missed_return;
      const button = node('button', '', `slot${slot.capacity ? '' : ' closed'}`);
      const details = `${shift.stations[code].name} ${time(slot.at)}，占用 ${slot.docked}，空桩 ${slot.free}，暂存 ${slot.held}，未成交 ${misses}`;
      button.title = details;
      button.setAttribute('aria-label', details);
      button.setAttribute('aria-pressed', String(selectedSlot?.at === slot.at && selectedSlot?.station === code));
      button.style.setProperty('--occupied', `${slot.capacity ? 100 * slot.docked / slot.capacity : 0}%`);
      const row = node('span', '', 'slot-label');
      row.append(node('span', slot.capacity ? `${slot.docked}/${slot.capacity}` : '关闭', 'num'));
      if (misses) row.append(node('span', `×${misses}`, 'slot-flag'));
      button.append(row, node('span', '', 'slot-meter'));
      button.addEventListener('click', () => {
        selectedSlot = slot;
        for (const item of chart.querySelectorAll('[aria-pressed]')) item.setAttribute('aria-pressed', String(item === button));
        onSlot();
      });
      grid.push(button);
    }
  }
  chart.replaceChildren(...grid);
}

function timeline(result, data, shift) {
  const station = names(shift);
  const focus = selectedSlot;
  $('slot-selection').textContent = focus ? `${station(focus.station)} · ${time(focus.at)} 起` : '全班次 · 按发生时点';
  $('clear-slot').hidden = !focus;
  let entries = result.timeline;
  if (focus) {
    const begin = Date.parse(focus.at);
    const end = begin + data.slot_minutes * 60000;
    entries = entries.filter(row => row.station === focus.station && begin <= Date.parse(row.at) && Date.parse(row.at) < end);
  }
  table('timeline', ['发生时点', '站点', '动作', '编号', '可借（辆）', '空桩', '暂存（辆）', '判定', '源行'], entries.map(row =>
    [clock(row.at), station(row.station), kind(row.kind), row.id, row.after.docked, row.after.free, row.after.held,
      ['rent','return'].includes(row.kind) ? outcome(row.code) : '生效', row.line]), '该时间段没有事件');
}

export function replay(results, shift, data) {
  const mode = $('replay-mode').value;
  const result = results[mode];
  const current = data[mode];
  const closing = Object.values(result.closing);
  kpis([['租还尝试', current.attempted, '笔'], ['成交', current.served, '笔'], ['未成交', current.missed.length, '笔', 'warn'],
    ['期末可借', closing.reduce((sum, row) => sum + row.docked, 0), '辆'], ['期末空桩', closing.reduce((sum, row) => sum + row.free, 0), '桩']]);
  $('slot-step').textContent = `每格 ${current.slot_minutes} 分钟 · 占用 / 容量`;
  tide(current, shift, () => timeline(result, current, shift));
  timeline(result, current, shift);
}

export function demand(data, shift) {
  const current = data[$('demand-mode').value];
  const station = names(shift);
  kpis([['观察尝试', current.attempted, '笔'], ['未成交', current.missed.length, '笔', 'warn'],
    ['未借出', current.missed.filter(row => row.kind === 'rent').length, '笔'],
    ['未还入', current.missed.filter(row => row.kind === 'return').length, '笔'], ['涉及站点', new Set(current.missed.map(row => row.station)).size, '站']]);
  const bands = Object.entries(current.reasons).map(([code, amount]) => {
    const cell = node('div', '', 'band');
    const caption = `${label(code)} · ${amount} 笔`;
    const bar = node('progress');
    bar.value = amount;
    bar.max = current.missed.length;
    bar.setAttribute('aria-label', caption);
    cell.append(node('span', caption), bar);
    return cell;
  });
  $('demand-bands').replaceChildren(...(bands.length ? bands : [node('span', '本场景需求全部成交', 'ok')]));
  table('demand-rows', ['时点', '站点', '事件号', '尝试', '原因', '原因码', '源行'], current.missed.map(row =>
    [clock(row.at), station(row.station), row.id, kind(row.kind), label(row.code), row.code, row.line]), '没有待核需求');
}

function diffCell(title, value, tone, aside = '') {
  const cell = node('div', '', 'diff-cell');
  cell.append(node('span', title, 'subtle'), node('strong', value, 'num ' + tone));
  if (aside) cell.append(node('span', aside, 'subtle'));
  return cell;
}

export function dispatch(data, shift, draft = false) {
  const result = data.comparison;
  const station = names(shift);
  kpis([['基准未成交', result.before, '笔'], ['方案未成交', result.after, '笔'], ['净差量', signed(result.delta), '笔', result.delta > 0 ? 'bad' : 'ok'],
    ['恢复成交', result.recovered, '笔', 'ok'], ['新增未成交', result.newly_missed, '笔', 'warn']]);
  $('compare-state').textContent = draft ? '草稿试算' : '已发布方案';
  $('station-compare').replaceChildren(...result.stations.map(row =>
    diffCell(station(row.station), `${row.before} → ${row.after}`, row.delta > 0 ? 'bad' : row.delta < 0 ? 'ok' : '', `差量 ${signed(row.delta)} 笔`)));
  table('attempt-compare', ['时点', '站点', '事件号', '尝试', '基准', '方案', '源行'], result.changes.map(row =>
    [clock(row.at), station(row.station), row.id, kind(row.kind), outcome(row.before), outcome(row.after), row.line]), '没有租还判定变化');
}

export function inventory(data, shift) {
  const row = data[$('inventory-mode').value];
  const station = names(shift);
  kpis([['期初全网', row.start_fleet, '辆'], ['期末全网', row.end_fleet, '辆'], ['期末在骑', row.road_end, '辆'],
    ['期末在途', row.in_transit_end, '辆'], ['勾稽状态', row.ok ? '相符' : '复核', '', row.ok ? 'ok' : 'bad']]);
  table('stock-rows', ['站点', '期初', '还入', '调入', '借出', '调出', '账面期末', '桩上', '暂存', '实际期末', '差额'],
    row.stations.map(item => [station(item.station), item.opening, item.return, item.unload, item.rent, item.load,
      item.expected, item.docked, item.held, item.closing, item.gap]));
  const gaps = [['全网', row.fleet_gap], ['在骑', row.road_gap], ['调拨', row.move_gap], ['收件', row.intake_gap],
    ['容量', row.capacity_gap], ['尝试', row.attempt_gap], ['边界异常', row.limits.length], ['流量异常', row.flow_errors.length]];
  $('audit-balances').replaceChildren(...gaps.map(([title, amount]) => diffCell(title, signed(amount), amount ? 'bad' : 'ok')));
}

export function runs(meta, openRun) {
  const {manifest, history} = meta;
  const active = history.find(row => row.active);
  const viewed = history.find(row => row.id === manifest.id);
  kpis([['已归档', history.length, '版'], ['所见班次', viewed.active ? '当前' : '历史'], ['规则版本', manifest.rule_version],
    ['未成交差量', signed(viewed.delta), '笔'], ['调拨行程', manifest.plan.length, '趟']]);
  $('restore').hidden = manifest.id === active.id;
  $('run-cost').textContent = `处理 ${manifest.elapsed_ms} ms`;
  table('input-digests', ['输入', '字节', 'SHA-256'], Object.entries(manifest.inputs).map(([name, file]) => [name, file.bytes, file.sha256]));
  table('historical', ['班次', '编号', '生成时间', '未成交差量', '状态', '操作'], history.map(row => {
    const button = node('button', row.id === manifest.id ? '正在查看' : '查看', 'btn');
    button.disabled = row.id === manifest.id;
    button.addEventListener('click', () => openRun(row.id));
    return [row.shift, row.id.slice(0, 12), `${date(row.generated_at)} ${clock(row.generated_at)}`, row.delta,
      row.active ? '当前班次' : '历史留档', button];
  }));
}
