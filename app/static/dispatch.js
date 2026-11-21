import {$, node, table} from './view.js';

// 班次使用固定的北京时间，输入框不读取浏览器所在时区。
const local = value => value ? new Date(Date.parse(value) + 8 * 3600000).toISOString().slice(0, 23).replace(/(\.000)$/, '') : '';
const apiTime = value => value ? `${value.length === 16 ? value + ':00' : value}+08:00` : '';

function choice(field, label, values, selected) {
  const element = node('select');
  element.dataset.field = field;
  element.setAttribute('aria-label', label);
  for (const [value, name] of values) {
    const option = node('option', name);
    option.value = value;
    option.selected = value === selected;
    element.append(option);
  }
  return element;
}

function input(field, label, type, value) {
  const control = node('input');
  control.type = type;
  control.dataset.field = field;
  control.setAttribute('aria-label', label);
  control.value = value;
  control.required = true;
  return control;
}

export function readDraft() {
  return [...$('leg-editor').querySelectorAll('tbody tr')].map(row => {
    const get = key => row.querySelector(`[data-field="${key}"]`).value;
    return {id: row.dataset.id, truck: get('truck'), from: get('from'), to: get('to'),
      depart: apiTime(get('depart')), arrive: apiTime(get('arrive')), count: get('count') === '' ? '' : Number(get('count'))};
  });
}

export function fillDraft(legs, shift, onEdit) {
  const stationList = Object.entries(shift.stations).map(([key, row]) => [key, row.name]);
  const trucks = Object.keys(shift.trucks).map(key => [key, key]);
  $('fleet-limits').textContent = `${Object.entries(shift.trucks).map(([key, row]) => `${key} 限 ${row.load_limit} 辆`).join(' · ')} · 最短 ${shift.min_travel_minutes} 分钟`;
  table('leg-editor', ['行程', '车辆', '装车站', '卸车站', '装车时间', '卸车时间', '辆数', '操作'], legs.map(leg => {
    const start = input('depart', `行程 ${leg.id} 装车时间`, 'datetime-local', local(leg.depart));
    const end = input('arrive', `行程 ${leg.id} 卸车时间`, 'datetime-local', local(leg.arrive));
    start.step = end.step = 'any';
    const count = input('count', `行程 ${leg.id} 辆数`, 'number', leg.count);
    count.min = '1';
    const remove = node('button', '移除', 'link');
    remove.type = 'button';
    remove.setAttribute('aria-label', `移除行程 ${leg.id}`);
    remove.addEventListener('click', () => {
      fillDraft(readDraft().filter(row => row.id !== leg.id), shift, onEdit);
      onEdit();
    });
    return [leg.id, choice('truck', `行程 ${leg.id} 车辆`, trucks, leg.truck), choice('from', `行程 ${leg.id} 装车站`, stationList, leg.from),
      choice('to', `行程 ${leg.id} 卸车站`, stationList, leg.to), start, end, count, remove];
  }), '新增行程或试算无调拨方案');
  for (const [index, row] of [...$('leg-editor').querySelectorAll('tbody tr')].entries()) row.dataset.id = legs[index].id;
}

export function newLeg(legs, shift) {
  const truck = Object.keys(shift.trucks)[0];
  const previous = legs.filter(leg => leg.truck === truck).at(-1);
  const origin = previous?.to || shift.trucks[truck].station;
  const start = previous?.arrive || shift.trucks[truck].available_at;
  let sequence = legs.length + 1;
  while (legs.some(leg => leg.id === `M-${sequence}`)) sequence++;
  return {id: `M-${sequence}`, truck, from: origin, to: Object.keys(shift.stations).find(code => code !== origin),
    depart: start, arrive: new Date(Date.parse(start) + shift.min_travel_minutes * 60000).toISOString(), count: 1};
}
