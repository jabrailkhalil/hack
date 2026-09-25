"""Render frozen accuracy and measured runtime evidence, never fit or select."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE='baseline_v2';FINAL='balanced_physics'


def read(path):return json.loads((ROOT/path).read_text())
def fmt(value,digits=6):return 'нет данных' if value is None else f'{value:.{digits}f}'
def gain(a,b):return None if a is None or b is None or a==0 else 100*(a-b)/a


def main():
    valid=read('reports/final/validation/results.json');test=read('reports/final/test/results.json')
    runtime=read('reports/final/runtime_full.json');execution=read('reports/final/runtime_execution.json')
    frozen=read('submission/FREEZE.json');test_execution=read('reports/final/final_test_execution.json')
    assert test['test_evaluated'] and test['bags']==22
    assert runtime['full_bag'] and runtime['correctness_failures']==[]
    assert test['source_sha256']==frozen['source_sha256']
    out=ROOT/'reports/final';cadence={}
    trace_path=out/'runtime_full.trace.csv'
    if trace_path.exists():
        with trace_path.open(newline='') as source:rows=list(csv.DictReader(source))
        arrivals=[max(int(r['velocity_received_ns']),int(r['position_received_ns'])) for r in rows]
        if len(arrivals)>1:
            gaps=[(b-a)/1e6 for a,b in zip(arrivals,arrivals[1:])]
            counts=Counter(int((a-arrivals[0])/1e9) for a in arrivals)
            last=int((arrivals[-1]-arrivals[0])/1e9)
            complete=[counts.get(i,0) for i in range(1,last)]
            cadence=dict(max_wall_gap_ms=max(gaps),gaps_above_250ms=sum(g>250 for g in gaps),
                complete_one_second_windows=len(complete),one_second_windows_below_10_outputs=sum(c<10 for c in complete),
                minimum_outputs_per_complete_second=min(complete) if complete else None)
    fields=['stage','bag','group','receiver','model','n','coverage','rmse','mae','bias','p95','integrated_error_m_not_xyz','full_span_terminal_error_m','full_span_terminal_drift_percent']
    with (out/'accuracy.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for stage,data in [('validation',valid),('test',test)]:
            for row in data['clean']:
                for receiver,models in row['receivers'].items():
                    for model,m in models.items():
                        item=dict(stage=stage,bag=row['bag'],group=row['group'],receiver=receiver,model=model)
                        item.update({k:m.get(k) for k in fields if k in m})
                        distance=m.get('distance_surrogate',{})
                        item.update({k:distance.get(k) for k in fields if k in distance})
                        writer.writerow(item)
    fields=['stage','bag','group','receiver','model','kind','start','end','n','coverage','rmse','event_rmse','mae','bias','p95','recovery_s','false_stop_samples']
    with (out/'faults.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for stage,data in [('validation',valid),('test',test)]:
            for row in data['stress']:
                for receiver,models in row['receivers'].items():
                    for model,m in models.items():
                        item=dict(stage=stage,bag=row['bag'],group=row['group'],receiver=receiver,model=model,**row['fault'])
                        item.update({k:m.get(k) for k in fields if k in m});writer.writerow(item)
    lines=['# Результаты финальной версии v4','','## Статус и границы результата','',
        'Сдаваемая конфигурация: fitted balanced_physics v3 + исправленный runtime v4, 20 Гц, alignment_delay_s=0. Проверен отложенный test после фиксации источников. Нового fitting/выбора модели по test не выполнялось. Положение — относительная дистанция (s,0,0), не восстановленная ENU/xyz-траектория. Это не официальный балл жюри.','',
        f"Freeze: `{frozen['source_ref']}`, создан {frozen['created_utc']}; {len(frozen['source_sha256'])} source/config/evaluator-хешей. Final-test run: [{test_execution['run_id']}](https://github.com/jabrailkhalil/hack/actions/runs/{test_execution['run_id']}).",'',
        'Train: 64 bag / 27 групп; validation: 19 / 10; final test: 22 / 10; development: 17 / 7. Все 22 test-bag обработаны, но не каждый содержит доступный GNSS-эталон. Метаданные разделения существовали до обучения.','',
        '## Точность скорости','',
        '`baseline_v2` ниже означает старые физические коэффициенты на **том же финальном runtime**, а не повтор старого исполняемого кода. Оба варианта имеют одинаковые stamps и маски сопоставления. GNSS master/rover сохранены отдельно. Group-macro: равный вес между группами, внутри группы среднее bag/receiver RMSE. Pooled RMSE объединяет доступные точки.','',
        '| Раздел | Показатель | Baseline | Финальная | Выигрыш, % |','|---|---|---:|---:|---:|']
    for stage,data in [('Validation',valid),('Final test',test)]:
        for label,key in [('Group-macro RMSE, м/с','group_macro_rmse'),('Pooled RMSE, м/с','pooled_rmse'),('RMSE в fault-окнах, м/с','group_macro_fault_event_rmse')]:
            a=data['summary'][BASE][key];b=data['summary'][FINAL][key]
            lines.append(f'| {stage} | {label} | {fmt(a)} | {fmt(b)} | {fmt(gain(a,b),2)} |')
    missing=test['summary'][FINAL]['missing_bag_receivers']
    lines += ['',f"Test: {test['summary'][FINAL]['samples']} сопоставленных точек, {test['summary'][FINAL]['groups_with_reference']} групп с reference. "+('Нет GNSS-метрики для: '+', '.join(missing)+'.' if missing else 'Во всех bag/receiver есть сопоставленные точки.'),'',
        'Сравнение с front/mean_scaled и точные общие маски сохранены в JSON/CSV. Их coverage может отличаться от observer при missing wheels; нельзя считать разницу pooled-ошибок на разных масках чистым выигрышем алгоритма.','',
        '### Каждый test-bag и каждый GNSS-приёмник','',
        '| Bag | Receiver | Baseline RMSE | Final RMSE | Bias final | Reference coverage | Outputs / expected ticks |','|---|---|---:|---:|---:|---:|---:|']
    for row in test['clean']:
        for receiver,models in row['receivers'].items():
            a=models[BASE];b=models[FINAL]
            lines.append(f"| {row['bag']} | {receiver} | {fmt(a['rmse'])} | {fmt(b['rmse'])} | {fmt(b.get('bias'))} | {100*b.get('coverage',0):.2f}% | {row['outputs']} / {row.get('expected_ticks','?')} |")
    lines += ['', 'Reference coverage — доля выпущенных оценок с сопоставимым GNSS, не процент времени всей записи. Outputs/expected ticks показаны отдельно; initial waiting и пропуски не заменяются нулевой ошибкой.','',
        '## Отказы и восстановление','',
        f"На test сформировано {test['fault_scenarios']} bag/scenario случаев: bias передней тележки 5 м/с на 5 с, dropout обеих на 5/10 с, lock обеих на 3 с. Место сбоя выбирается только по wheel-данным, эталон не изменяется. Recovery требует непрерывного окна 1 с с |ошибкой|<0.25 м/с; при отсутствии восстановления в наблюдаемом 10-секундном окне записывается null. Полные показатели, включая неудачные случаи, находятся в [faults.csv](../reports/final/faults.csv)."]
    for name in (BASE,FINAL):
        scores=[models[name] for row in test['stress'] for models in row['receivers'].values() if models[name]['rmse'] is not None]
        not_recovered=sum(s.get('recovery_s') is None for s in scores);false_stops=sum(s.get('false_stop_samples',0) for s in scores)
        lines += ['',f"{name}: {len(scores)} сравнений с reference; без подтверждённого восстановления — {not_recovered}; false-stop samples — {false_stops}."]
    full=[]
    for row in test['clean']:
        for receiver,models in row['receivers'].items():
            d=models[FINAL].get('distance_surrogate',{})
            if d.get('full_span_terminal_drift_percent') is not None:full.append((row['bag'],receiver,d))
    lines += ['', '## Положение: только явно обозначенная скалярная проверка','',
        'Сравнивается s с интегралом горизонтальной GNSS-скорости. **Это не xyz, не cross-track и не доказательство 3D-точности.** Full-span scalar drift вычисляется только при непрерывном reference на всём интервале опубликованных оценок и дистанции >1 м. При gaps он равен null; отдельные непрерывные reference-spans имеют явную переустановку reference-origin в evaluator, не reset ноды.','',
        f'Полная скалярная проверка доступна для {len(full)} bag/receiver интервалов. Остальные не объявляются нулевым дрейфом.','',
        '| Bag | Receiver | Reference distance, м | Terminal scalar error, м | Scalar drift, % |','|---|---|---:|---:|---:|']
    for bag,receiver,d in full:
        lines.append(f"| {bag} | {receiver} | {fmt(d['full_span_reference_distance_m'],2)} | {fmt(d['full_span_terminal_error_m'],3)} | {fmt(d['full_span_terminal_drift_percent'],3)} |")
    lines += ['', '## Реальная ROS-производительность','',
        f"Полный development bag `{runtime['bag']}`, {runtime['measured_duration_s']:.3f} с при 1x. [Run {execution['run_id']}](https://github.com/jabrailkhalil/hack/actions/runs/{execution['run_id']}), исходный commit `{execution['source_commit']}`. Весь контейнер ограничен {execution['cpu_limit']} CPU и {execution['memory_limit_bytes']} байт, сеть — {execution['network']}. Эта запись не принадлежит final test. Измерения с optional trace включают его накладные расходы.",'',
        '| Показатель | Измерено |','|---|---:|',
        f"| Продолжительность, с | {runtime['measured_duration_s']:.3f} |",
        f"| Velocity / position outputs | {runtime['outputs']} / {runtime['position_outputs']} |",
        f"| Source / wall rate, Гц | {runtime['source_rate_hz']:.3f} / {runtime['wall_rate_hz']:.3f} |",
        f"| Peak RSS ноды и launcher, MiB | {runtime['rss_peak_bytes']/2**20:.2f} |",
        f"| CPU p95 / max, эквиваленты ядра | {runtime['cpu_core_equivalents']['p95']:.3f} / {runtime['cpu_core_equivalents']['max']:.3f} |",
        f"| Backward resets / causal errors | {runtime['final_diagnostics'].get('backward_clock_resets','?')} / {runtime['causal_errors']} |",
        f"| Непривязанные входы / уникальные отправленные | {runtime['uncredited_inputs']} / {runtime['unique_offered']} |"]
    if cadence:
        lines += [f"| Max wall gap между результатами, мс | {cadence['max_wall_gap_ms']:.2f} |",
            f"| Wall gaps >250 мс | {cadence['gaps_above_250ms']} |",
            f"| Полные 1-с окна с <10 выходами / всего | {cadence['one_second_windows_below_10_outputs']} / {cadence['complete_one_second_windows']} |"]
    pipe=runtime['callback_to_publish_ms_after_10s'];external=runtime['publisher_to_both_result_subscribers_ms_after_10s'];all_ext=runtime['publisher_to_both_result_subscribers_ms_all']
    for label,x in [('Callback→publish после 10 с',pipe),('Publisher→оба subscribers после 10 с',external),('Publisher→оба subscribers, включая старт',all_ext)]:
        lines += [f"| {label}: p50 / p95 / p99 / max, мс | {fmt(x['p50'],2)} / {fmt(x['p95'],2)} / {fmt(x['p99'],2)} / {fmt(x['max'],2)} |"]
    lines += ['', 'Timing означает первое соответствующее обработке held input сообщение обоих выходов. Непривязанные входы перечислены, а не получили фиктивную нулевую задержку. Обработанные rejected inputs не означают принятые фильтром измерения. Пороги 100/250 мс проверяются по наблюдаемым распределениям; это не hard real-time гарантия каждого будущего сообщения.','',
        f"Флаг измеренной проверки (p95 steady ≤100 мс и max all ≤250 мс): **{runtime['latency_observed_within_nominal_and_peak']}**. Номинальный лимит жюри относится к задержке, а не только p95; единичные превышения 100 мс ниже 250 мс должны рассматриваться как пиковая деградация, не скрываться.",'',
        'Старый pilot с delay=60 мс не прошёл nominal: p95 около158 мс. После delay=0 сохранены два новых clock-pilot. Снижение намеренной задержки имеет компромисс по качеству: историческая v3 validation RMSE не переносится автоматически на новый runtime; новая validation приведена выше.','',
        'Полные JSON, trace CSV, resources CSV и node logs находятся в `reports/final/`. Конечное сравнение RSS: '+f"первая стабильная медиана {runtime['rss_median_first_window_bytes']} байт; последняя {runtime['rss_median_last_window_bytes']} байт. Один полный прогон не доказывает отсутствие утечек при неограниченной работе.",'',
        '## Воспроизводимость и сдача','',
        'Исходники и коэффициенты проверяются по FREEZE, состав standalone ZIP — по MANIFEST. Unit/research-integrity и реальные ROS launch/fault-сценарии выполняются отдельно; build из ZIP проверяется offline. Архив содержит шесть обязательных материалов, но отправка формы и изменение доступа приватного репозитория не выполнялись. Не подтверждены организатором единицы/xyz-контракт, нет разрешённой карты. Подробности — [LIMITATIONS.md](LIMITATIONS.md).','']
    (ROOT/'submission/RESULTS.md').write_text('\n'.join(lines))
    summary=dict(test=test['summary'],validation=valid['summary'],runtime=dict(source_ref=execution['source_commit'],run_id=execution['run_id'],
        outputs=runtime['outputs'],wall_rate_hz=runtime['wall_rate_hz'],latency_ms=external,latency_all_ms=all_ext,rss_peak_bytes=runtime['rss_peak_bytes']),
        cadence=cadence,freeze_sha256=hashlib.sha256((ROOT/'submission/FREEZE.json').read_bytes()).hexdigest(),position='relative_1d, no xyz claim')
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
