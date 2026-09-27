'use strict';
const $ = id => document.getElementById(id);
const state = {contract: null, bags: [], runs: [], route: null};
const theme = new URLSearchParams(location.search).get('theme');
document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
const nf = (x, digits = 6) => x == null ? 'нет данных' : Number(x).toLocaleString('ru-RU', {maximumFractionDigits: digits});
function element(tag, text, cls) { const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node; }
function status(text, error = false) { $('status').textContent = text; $('status').className = error ? 'notice error' : 'muted'; }
async function api(path, body) {
  const response = await fetch('/api/v1' + path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!response.ok) { let reason = ''; try { reason = (await response.json()).detail; } catch { reason = response.statusText; } throw new Error(typeof reason === 'string' ? reason : JSON.stringify(reason)); }
  return response.json();
}
async function busy(id, work) { const button = $(id); button.disabled = true; try { await work(); } catch (e) { status(e.message, true); } finally { button.disabled = false; updateEnable(); } }
function eligible(id) { return state.contract?.development.some(b => b.bag === id); }
function scope(id) { return $('vehicle').value === 'all' || id.startsWith($('vehicle').value + '_'); }
function options(select, values, selected) { select.replaceChildren(); values.forEach(([value, title]) => {const option = element('option', title); option.value = value; select.append(option);}); if (values.some(([v]) => v === selected)) select.value = selected; }
function updateBags() {
  const previous = new Set([...$('bags').querySelectorAll('input:checked')].map(x => x.value));
  $('bags').replaceChildren();
  state.bags.filter(b => eligible(b.id) && scope(b.id)).forEach(b => {
    const label = element('label'); const input = element('input'); input.type = 'checkbox'; input.value = b.id; input.checked = previous.has(b.id);
    label.append(input, document.createTextNode(b.id)); $('bags').append(label);
  });
  if (!$('bags').children.length) $('bags').append(element('p', 'Нет доступных поездок этой области с закреплёнными development ID.'));
  updateLocalBags();
}
function runIds(run) { return (run?.metrics?.bags || []).map(b => b.id); }
function updateLocalBags() {const run = state.runs.find(r => r.id === $('localize-run').value); options($('localize-bag'), runIds(run).filter(id => eligible(id) && scope(id)).map(id => [id, id]), $('localize-bag').value); updateEnable();}
function updateEnable() {$('localize').disabled = !state.route || !$('localize-bag').value;}
async function refresh() {
  const data = await Promise.all([api('/research/contract'), api('/dataset'), api('/runs')]);
  [state.contract, state.bags, state.runs] = [data[0], data[1].bags, data[2]];
  updateBags();
  const choices = state.runs.filter(r => runIds(r).some(eligible)).map(r => [r.id, r.id]);
  for (const id of ['baseline-run','candidate-run','localize-run']) options($(id), choices, $(id).value);
  const pick = kind => state.runs.find(r => runIds(r).some(eligible) && (kind === 'candidate' ? Number(r.config?.estimator?.core?.max_power_w) === 429127.7144908343 : r.config?.estimator?.profile === 'hack_v8' && Number(r.config?.estimator?.core?.max_power_w) === 280873.5334860941));
  if (pick('baseline')) $('baseline-run').value = pick('baseline').id;
  if (pick('candidate')) $('candidate-run').value = pick('candidate').id;
  updateLocalBags();
  const box = $('contract'); box.replaceChildren();
  box.append(element('p', 'Источник: предоставленная пользователем суммаризация. Ссылки на сообщения внутри неё не раскрыты; оригинальный чат не включён.'));
  box.append(element('p', 'Цель: 30618, те же два маршрута, движение вперёд. Дополнительные GNSS могут полностью отсутствовать.'));
  box.append(element('p', 'TF относительно base_link: master (−9.873, 0, 3) м; rover (2.563, 0, 3) м. Между осями тележек 7.55 м. Плечо поворачивается по касательной маршрута; roll=0 — допущение.'));
  state.contract.unresolved.forEach(text => box.append(element('p', text, 'small muted')));
  status('Готово. Запуски и результаты не создаются автоматически.');
}
$('refresh').onclick = () => busy('refresh', refresh);
$('vehicle').onchange = () => {updateBags(); $('compare-result').replaceChildren(); $('localize-result').replaceChildren();};
$('localize-run').onchange = updateLocalBags;
$('all-bags').onclick = () => $('bags').querySelectorAll('input').forEach(input => {input.checked = true;});
$('enqueue').onclick = () => busy('enqueue', async () => {
  const bags = [...$('bags').querySelectorAll('input:checked')].map(x => x.value);
  if (!bags.length) throw new Error('Выберите development-поездки.');
  let faults = [];
  if ($('fault-kind').value === 'dropout') {
    const start_s = Number($('fault-start').value), end_s = Number($('fault-end').value);
    if (!(start_s >= 0 && end_s > start_s)) throw new Error('Проверьте начало и конец отказа.');
    faults = [{kind: 'drop', topics: ['/vehicle/front_bogie_velocity', '/vehicle/rear_bogie_velocity'], start_s, end_s, probability: 1}];
  }
  const job = await api('/research/enqueue', {bags, faults});
  $('queue-result').textContent = `Задание ${job.id}: ${job.status}. Прогресс доступен в «Эксперименты». После завершения обновите список запусков.`;
  status('Парное задание добавлено в существующую очередь.');
});
function table(headers, rows) { const wrapper = element('div', null, 'scroll'); const t = element('table'); const head = element('tr'); headers.forEach(v => head.append(element('th', v))); const th = element('thead'); th.append(head); t.append(th); const body = element('tbody'); rows.forEach(values => {const row = element('tr'); values.forEach(v => row.append(element('td', String(v)))); body.append(row);}); t.append(body); wrapper.append(t); return wrapper; }
$('compare').onclick = () => busy('compare', async () => {
  const baseline = $('baseline-run').value, candidate = $('candidate-run').value;
  if (!baseline || !candidate || baseline === candidate) throw new Error('Выберите два разных сохранённых запуска.');
  const a = state.runs.find(r => r.id === baseline), b = state.runs.find(r => r.id === candidate);
  const bags = [...new Set([...runIds(a), ...runIds(b)])].filter(eligible);
  const missing = bags.filter(id => scope(id) && (!runIds(a).includes(id) || !runIds(b).includes(id)));
  if (missing.length) throw new Error('Неполная парная область: ' + missing.join(', ') + '. Запустите обе модели на одном наборе.');
  const data = await api('/research/compare', {baseline, candidate, bags, vehicle: $('vehicle').value});
  const target = $('compare-result'); target.replaceChildren();
  target.append(element('p', `Область: ${data.scope}. ${data.rows.length} общих поездок. Это reused development и лабораторный speed proxy, не официальный XYZ score.`, 'notice'));
  const s = data.summary;
  target.append(table(['Скорость, м/с','Baseline','Кандидат'], [['Group-macro RMSE', nf(s.baseline.group_macro_rmse_mps), nf(s.candidate.group_macro_rmse_mps)], ['Pooled RMSE',nf(s.baseline.pooled_rmse_mps),nf(s.candidate.pooled_rmse_mps)], ['Сопоставленные отсчёты',s.baseline.samples,s.candidate.samples]]));
  target.append(table(['Поездка','RMSE baseline','RMSE кандидат','Изменение ошибки, %','Отсчёты'],data.rows.map(r => [r.bag,nf(r.baseline.rmse_mps),nf(r.candidate.rmse_mps),r.baseline.rmse_mps > 0 ? nf(100*(r.candidate.rmse_mps/r.baseline.rmse_mps-1),2) : 'нет данных',r.baseline.count])));
  status('Сравнение готово. Положительная дельта означает ухудшение; автоматического выбора победителя нет.');
});
$('route-file').onchange = async () => {
  state.route = null; updateEnable(); $('route-badge').textContent = 'Pathgraph не загружен';
  const file = $('route-file').files[0]; if (!file) return;
  try {
    if (file.size > 2200000) throw new Error('Файл маршрута превышает 2.2 MB.');
    const route = JSON.parse(await file.text());
    if (route.schema !== 'tram-route-enu-v1' || route.frame !== 'ENU' || route.reference_point !== 'base_link' || !Array.isArray(route.paths)) throw new Error('Требуется явный tram-route-enu-v1, ENU, base_link. Исходный формат Pathgraph не угадывается.');
    state.route = route;
    options($('path'), [['','Автовыбор с отказом при неоднозначности'], ...route.paths.map(p => [p.id,p.id])], '');
    $('route-badge').textContent = file.name;
    $('route-info').textContent = `Путей: ${route.paths.length}. Origin: ${JSON.stringify(route.origin_wgs84)}. Источник: ${route.source}. Полная проверка выполняется сервером до replay.`;
    status('Внешняя геометрия загружена. Её статус как официальной карты автоматически не подтверждается.');
  } catch (e) {state.route = null; status(e.message,true);} updateEnable();
};
const NS = 'http://www.w3.org/2000/svg';
function svgElement(name, attrs) {const el=document.createElementNS(NS,name); Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v))); return el;}
function plot(label, lines, equalAspect = false) {
  const container=element('div');container.append(element('h3',label));const svg=svgElement('svg',{viewBox:'0 0 600 300',role:'img','aria-label':label});container.append(svg);
  const pairs=lines.flatMap(l=>l.values).filter(p=>p && p.every(Number.isFinite));
  if (!pairs.length) {container.append(element('p','Нет локализованных точек. Проверьте журнал отказов.','muted'));return container;}
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity; for(const p of pairs){minX=Math.min(minX,p[0]);maxX=Math.max(maxX,p[0]);minY=Math.min(minY,p[1]);maxY=Math.max(maxY,p[1]);}
  if (maxX-minX<1) {const center=(maxX+minX)/2;minX=center-.5;maxX=center+.5;}
  if (maxY-minY<1) {const center=(maxY+minY)/2;minY=center-.5;maxY=center+.5;}
  if (equalAspect) {const scale=Math.max((maxX-minX)/535,(maxY-minY)/235);const cx=(minX+maxX)/2,cy=(minY+maxY)/2;minX=cx-scale*535/2;maxX=cx+scale*535/2;minY=cy-scale*235/2;maxY=cy+scale*235/2;}
  const x=v=>45+(v-minX)/Math.max(1,maxX-minX)*535,y=v=>265-(v-minY)/Math.max(1,maxY-minY)*235;
  for(let i=0;i<=4;i++){const yy=30+i*235/4;svg.append(svgElement('line',{x1:45,x2:580,y1:yy,y2:yy,stroke:'currentColor',opacity:.1}));const text=svgElement('text',{x:3,y:yy+4,fill:'currentColor','font-size':10});text.textContent=nf(maxY-i*(maxY-minY)/4,1);svg.append(text);}
  lines.forEach(line=>{let segment=[];const flush=()=>{if(segment.length>1)svg.append(svgElement('polyline',{points:segment.join(' '),fill:'none',stroke:line.color,'stroke-width':line.width||2}));segment=[];};line.values.forEach(p=>{if(!p||!p.every(Number.isFinite)){flush();return;}segment.push(`${x(p[0])},${y(p[1])}`);});flush();});
  const text=svgElement('text',{x:45,y:289,fill:'currentColor','font-size':10});text.textContent=`${nf(minX,1)} → ${nf(maxX,1)}`;svg.append(text);return container;
}
$('localize').onclick = () => busy('localize', async () => {
  if (!state.route) throw new Error('Сначала загрузите внешний маршрут.');
  status('Выполняется отдельный replay привязки. Исходный эксперимент не изменяется.');
  const data = await api('/research/localize', {run:$('localize-run').value,bag:$('localize-bag').value,route:state.route,path:$('path').value,receiver:$('receiver').value,period_s:Number($('period').value),policy:{gain:Number($('gain').value),max_correction_m:Number($('correction').value),initial_window_s:Number($('initial-window').value)}});
  const target=$('localize-result');target.replaceChildren();
  target.append(element('p',`${data.total_points} тактов. GNSS корректирует только привязку: скорость и raw s сохранены. Независимый XYZ RMSE не рассчитан.`, 'notice'));
  const metrics=element('div',null,'metrics');for (const [label,value] of [['Инициализации',data.counts.sparse.initialized||0],['Коррекции',data.counts.sparse.corrected||0],['Отказы/пропуски',Object.entries(data.counts.sparse).filter(([k])=>!['initialized','corrected'].includes(k)).reduce((s,[,v])=>s+v,0)]]){const m=element('div',label,'metric');m.append(element('b',String(value)));metrics.append(m);}target.append(metrics);
  target.append(element('p','Синий: sparse GNSS. Янтарный: только initial GNSS. Серый: внешний маршрут. График s — координата привязки, не заново интегрированная скорость.','legend'));
  const views=element('div',null,'visuals');const origin=data.points.length?BigInt(data.points[0].time_ns):0n;
  const segmented = (mode, value) => data.points.flatMap((p,i) => {
    const split = i > 0 && p[mode].segment_id !== data.points[i-1][mode].segment_id;
    return split ? [null, value(p)] : [value(p)];
  });
  const routeLines=state.route.paths.map(p=>({color:'#7b8794',width:1,values:p.points.map(v=>v.slice(0,2))}));
  views.append(plot('Положение ENU, метры',[...routeLines,...['initial_only','sparse'].map((mode,i)=>({color:i?'#508dec':'#d99a28',values:segmented(mode,p=>p[mode].xyz?.slice(0,2)||null)}))],true));
  views.append(plot('Координата маршрута s(t), секунды / метры',['initial_only','sparse'].map((mode,i)=>({color:i?'#508dec':'#d99a28',values:segmented(mode,p=>p[mode].route_s==null?null:[Number(BigInt(p.time_ns)-origin)/1e9,p[mode].route_s])}))));target.append(views);
  target.append(element('h3','Журнал GNSS: первые 100 решений sparse'));
  target.append(table(['Source t, с','Причина','Поправка, м'],data.corrections.filter(r=>r.mode==='sparse').slice(0,100).map(r=>[nf(Number(BigInt(r.stamp_ns)-origin)/1e9,2),r.reason,nf(r.correction_m,3)])));
  const download=element('a','Полный JSON: все точки, решения, параметры и хеши');download.href='/api/v1/download?run='+encodeURIComponent(data.artifact_run)+'&file=result.json';target.append(download);
  status('Replay привязки завершён. Результат сохранён отдельно; победа по точности не заявляется.');
});
refresh().catch(e=>status(e.message,true));
