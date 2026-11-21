export const $ = id => document.getElementById(id);
const reasons = JSON.parse($('reason-labels').textContent);
const kinds = {rent: '借车', return: '还车', capacity: '容量切换', load: '装车', unload: '卸车'};
const localClock = options => new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', hourCycle: 'h23', ...options});
const hhmm = localClock({hour: '2-digit', minute: '2-digit'});
const precise = localClock({hour: '2-digit', minute: '2-digit', second: '2-digit'});
const day = localClock({year: 'numeric', month: '2-digit', day: '2-digit'});

export const time = value => hhmm.format(new Date(value));
export const clock = value => precise.format(new Date(value));
export const date = value => day.format(new Date(value));
export const kind = value => kinds[value] || value;
export const label = code => reasons[code] || code;
export const signed = value => value > 0 ? `+${value}` : String(value);

export async function api(url, options) {
  const response = await fetch(url, {cache: 'no-store', ...options});
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.message), data);
  return data;
}

export function post(url, data) {
  return api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
}

export function node(tag, text = '', style = '') {
  const element = document.createElement(tag);
  element.className = style;
  element.textContent = text;
  return element;
}

export function table(id, headers, rows, empty = '暂无记录') {
  const target = $(id);
  if (!rows.length) {
    target.replaceChildren(node('p', empty, 'empty'));
    return;
  }
  const element = node('table', '', 'ledger');
  const heading = element.createTHead().insertRow();
  for (const title of headers) {
    const cell = node('th', title);
    cell.scope = 'col';
    heading.append(cell);
  }
  const body = element.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) {
      const cell = tr.insertCell();
      if (value instanceof Node) cell.append(value);
      else if (typeof value === 'number') {
        cell.textContent = value;
        cell.className = 'num';
      } else {
        cell.textContent = value ?? '—';
        cell.title = cell.textContent;
      }
    }
  }
  target.replaceChildren(element);
}

export function kpis(rows) {
  $('kpis').replaceChildren(...rows.map(([title, value, unit = '', tone = '']) => {
    const cell = node('div', '', 'kpi');
    const number = node('strong', value, `num ${tone}`);
    if (unit) number.append(node('span', unit, 'kpi-unit'));
    cell.append(node('span', title, 'kpi-label'), number);
    return cell;
  }));
}

export function notice(text = '', error = false, refresh = false) {
  $('notice').hidden = !text;
  $('notice').dataset.error = error;
  $('notice-text').textContent = text;
  $('refresh').hidden = !refresh;
}

export function showError(error, recovery = false) {
  const {leg, line, station, available, requested} = error.details || {};
  const detail = [leg, line ? `第 ${line} 行` : '', station, available !== undefined && requested !== undefined ? `${available}/${requested} 辆` : ''].filter(Boolean);
  notice(`${error.message || '请求失败，请重试'}${detail.length ? ` · ${detail.join(' · ')}` : ''}`, true, recovery || error.code === 'STALE_RUN');
}

export function outcome(code) {
  return node('span', code ? label(code) : '成交', code ? 'bad' : 'ok');
}
