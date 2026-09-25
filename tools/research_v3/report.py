"""Export evidence and selected launch configuration; never edit the estimator."""
from collections import Counter
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import numpy as np
from experiment import ROOT,REPORTS,MODELS,Store,replay,Config,match,metrics,write_json
from manifest import digest


def main():
    decision=json.loads((REPORTS/'decision.json').read_text())
    data=json.loads((REPORTS/'validation.json').read_text())
    train=json.loads((REPORTS/'training.json').read_text());store=Store()
    winner=decision['selected'];configs={n:Config(**json.loads((MODELS/(n+'.json')).read_text())['config'])
        for n in ['baseline_v2',winner]}
    # Supplementary open-loop comparator; cannot change preregistered selection.
    open_loop=[]
    for bag in store.plan['splits']['validation']:
        events,refs=store.load(bag,'validation')
        for name,c in configs.items():
            a,counts=replay(events,c,model_only=True)
            if not len(a):continue
            open_loop.append(dict(bag=bag,model=name,outputs=len(a),**counts,receivers={rx:metrics(
                a[:,0],a[:,1],match(ref,a[:,0]),np.ones(len(a),bool)) for rx,ref in refs.items()}))
    write_json(REPORTS/'open_loop.json',dict(note='No wheel correction after initial wheel seed; no reset/teacher forcing. Not used for selection.',results=open_loop,access=store.access))
    params=json.loads((MODELS/(winner+'.json')).read_text())
    if winner!='baseline_v2' and not (params['solver_success'] and decision['candidates'][winner]['eligible']):
        raise ValueError('Cannot export failed candidate')
    header='# Selected on grouped validation, NOT final test; see reports/research_v3/REPORT.md.\n'
    header+='# Effective physics in a fixed mass/radius gauge; wheel units 1/3.6 remain an organizer question.\n'
    selected=ROOT/'src/reserve_odometry/config/calibrated_v3.yaml'
    selected.write_text(header+(MODELS/(winner+'.yaml')).read_text())
    (ROOT/'src/reserve_odometry/config/default.yaml').write_text(selected.read_text())
    source_hashes={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'tools/research_v3').glob('*.py'))}
    source_hashes.update({str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'src/reserve_odometry/reserve_odometry').glob('*.py'))})
    write_json(REPORTS/'provenance.json',dict(source_commit=os.environ.get('GITHUB_SHA','local-working-tree'),
        source_sha256=source_hashes,plan=store.plan,default_candidate=winner,
        inference_core_unchanged_from=store.plan['base_commit'],test_payloads_evaluated=0,
        ci_run=os.environ.get('GITHUB_RUN_ID'),note='ROS promotion must additionally pass pull-request CI'))
    flat=[]
    for row in data['clean']:
        for rx,scores in row['receivers'].items():
            for name,m in scores.items():flat.append(dict(bag=row['bag'],group=row['group'],receiver=rx,model=name,
                rmse=m['rmse'],mae=m.get('mae'),bias=m.get('bias'),n=m['n'],coverage=m['coverage']))
    with (REPORTS/'leaderboard.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    group_errors={}
    for row in data['clean']:
        for rx,s in row['receivers'].items():
            if s['baseline_v2']['rmse'] is not None:
                group_errors.setdefault(row['group'],[]).append([s['baseline_v2']['rmse'],s[winner]['rmse']])
    pairs=np.array([np.mean(x,axis=0) for x in group_errors.values()]);rng=np.random.default_rng(20260925)
    samples=pairs[rng.integers(0,len(pairs),size=(10000,len(pairs)))].mean(axis=1)
    gains=(samples[:,0]-samples[:,1])/samples[:,0]
    interval=np.quantile(gains,[.025,.975]).tolist()
    write_json(REPORTS/'group_bootstrap.json',dict(groups=len(pairs),draws=10000,seed=20260925,
        relative_rmse_gain_95pct_interval=interval,note='Descriptive paired-group bootstrap AFTER candidate selection, not confirmatory test evidence'))
    no_reference=[r['bag'] for r in data['clean'] if all(x['baseline_v2']['rmse'] is None for x in r['receivers'].values())]
    lines=['# Калибровка v3: обучение и проверка гипотез','',
        '## Итог','',f'Выбран `{winner}`. Коэффициенты экспортированы в `config/calibrated_v3.yaml` и launch-default; слияние допускается только после ROS CI. Финальный test не запускался.','',
        'Обучены три варианта одной аналитической модели: только тяговые/тормозные коэффициенты (`gain_only`); семь эффективных параметров (`nonlinear_physics`); те же параметры с балансировкой тяги/торможения/нейтрали (`balanced_physics`). Фильтр, пороги, синхронизация, масштаб колёс и код оценивателя не подбирались.','',
        '## Разделение и доступ','',
        '| Раздел | Прогоны | Независимые группы |','|---|---:|---:|']
    for role,bags in store.plan['splits'].items():lines.append(f'| {role} | {len(bags)} | {len(set(store.records[b]["group"] for b in bags))} |')
    lines += ['', 'Записи группируются по пересечению source/record timestamps и соседству до 60 с, а также по точным SHA256 баз и непрозрачным отпечаткам vehicle-payload без времени. Группа, содержащая ранее просмотренный smoke-bag, целиком остаётся development. Это предотвращает попадание известных фрагментов в validation/test, но не доказывает отсутствие всех возможных семантических дубликатов.','',
        f'Из {len(store.plan["splits"]["train"])} train-bag загружены только три `/vehicle/*` топика. Отобрано **{train["train_samples"]}** обучающих точек в **{sum(s["selected"]>0 for s in train["stats"])}** прогонах. Данные GNSS не использованы в fitting. Target - offline-производная средней скорости двух согласованных колёс: сетка 0.1 с, окно 11 точек, разница тележек <0.15 м/с, скорость 0.4..35 м/с, |ускорение|<2.5 м/с². Симметричное окно используется только в train-target; runtime его не использует.','',
        'Store запрещает открывать test для train/validation до обращения к SQLite. Метаданные и хеши test нужны для разделения; значения не декодировались для обучения или оценки. Это программная защита исследовательского runner, не изоляция от владельца репозитория, способного изменить код.','',
        '## Validation: основной критерий','',
        'Одинаковая сетка прогнозов для всех вариантов; ближайшая GNSS-метка с допуском 50 мс. GNSS-speed = hypot(x,y), оба приёмника отдельно, без подбора приёмника по ошибке. RMSE агрегируется сначала внутри группы (записи и приёмники), затем одинаковым весом между группами. Это не балл официального судьи.','',
        '| Вариант | Group-macro RMSE скорости, м/с | RMSE в fault-окнах, м/с | Решение |','|---|---:|---:|---|']
    for name,m in decision['candidates'].items():lines.append(f'| {name} | {m["macro_group_rmse"]:.6f} | {m["macro_fault_event_rmse"]:.6f} | '+('допущен' if m['eligible'] else ', '.join(m['rejection_reasons']))+' |')
    lines += ['',f'Доступны {decision["validation_receiver_pairs"]} пар bag/receiver. Без GNSS-метрики: '+', '.join(no_reference)+'. Они не считаются нулевой ошибкой.',
        '',f'Описательный paired-group bootstrap после выбора кандидата: 95%-интервал относительного выигрыша **{100*interval[0]:.2f}..{100*interval[1]:.2f}%** ({len(pairs)} групп). Это не независимая проверка значимости после отбора модели.','',
        'Исходный восьмипрогонный smoke не является validation в этом цикле. Ранее опубликованные числа также нельзя напрямую сравнивать с этой таблицей: здесь другой набор, общий clock относительно целочисленного origin, а пропавшие колёса не исключаются из оценки самого observer.','',
        '## Сбои на реальных validation-записях','',
        'Для каждого bag выбирается первый разрешёнными wheel-данными движущийся участок после 10% записи, с 20 с разогрева и 10 с наблюдения восстановления. Место сбоя не зависит от GNSS и ошибок кандидата. Инъекции не меняют эталон.','',
        '| Сбой | Baseline event RMSE, м/с | Выбранный event RMSE, м/с |','|---|---:|---:|']
    for kind,duration in [('bias',5),('dropout',5),('dropout',10),('lock',3)]:
        group_values={}
        for row in data['stress']:
            if row['fault']['kind']!=kind or round(row['fault']['end']-row['fault']['start'])!=duration:continue
            for s in row['receivers'].values():
                if s['baseline_v2']['event_rmse'] is not None:group_values.setdefault(row['group'],[]).append([s['baseline_v2']['event_rmse'],s[winner]['event_rmse']])
        value=np.mean([np.mean(v,axis=0) for v in group_values.values()],axis=0)
        lines.append(f'| {kind}, {duration} с | {value[0]:.6f} | {value[1]:.6f} |')
    lines += ['',f'Создано {len(data["stress"])} bag/scenario случаев, из них {decision["stress_receiver_cases"]} сравнений с доступным приёмником. Recovery определяется как первое окно 1 с с |ошибкой|<0.25 м/с; отсутствие такого окна записывается null, не как нулевое время. Полные показатели, ложные остановки и missing reference сохранены в JSON.','',
        '## Параметры и математический смысл','',
        'Подбираются Fmax/m, Pmax/m, Bmax/m, Rroll/m, Rquad/m, показатель нелинейности notch и постоянная времени привода. Масса, радиус, КПД и передаточное отношение фиксированы как gauge; экспортированный момент не является оценкой реального паспортного момента.','',
        '| Параметр | Значение выбранной модели |','|---|---:|']
    for key,value in zip(train['parameters'],params['theta']):lines.append(f'| {key} | {value:.9g} |')
    lines += ['', 'Нулевой/почти нулевой quadratic resistance оказался на границе разрешённого диапазона. Нельзя интерпретировать это как доказательство отсутствия аэродинамического сопротивления. Коэффициенты оценивают эффективную динамику данного train-набора.','',
        '## Ограничения','',
        'Это модель, обученная на колёсной псевдоразметке. Одинаковое проскальзывание двух тележек может загрязнять target; фильтры качества не дают независимой истины. GNSS validation неоднороден: сохранены оба приёмника без постфактум удаления неудобных выбросов. Ошибка масштаба колёс 1/3.6 и правила координат требуют ответа организатора.','',
        '22 test-bag остаются без оценки. Не выполнены cross-vehicle-only обучение, полноценная 3D-оценка, длительный end-to-end latency benchmark или доказательство устойчивости к произвольному common-mode slip. Integrated speed error - не ошибка xyz. Open-loop comparator не использовался для выбора.','',
        'Код runtime остаётся причинным и без SciPy/numpy/LLM. Это конечный runner четырёх заранее заданных гипотез, не уже запущенный автономный консилиум агентов или RunPod-кластер.','',
        '## Воспроизведение','',
        'Исследования выполняются в отдельном Python 3.13 окружении. Не устанавливать requirements-research.txt в системный Python 3.10 ROS Humble.','',
        '```bash','python3 tools/get_dataset.py','python3.13 -m venv .venv-research','source .venv-research/bin/activate','python -m pip install -r requirements-research.txt',
        'python tools/research_v3/manifest.py dataset/data research/split_v3.json',
        'OPENBLAS_NUM_THREADS=1 python tools/research_v3/experiment.py --stage fit',
        'OPENBLAS_NUM_THREADS=1 python tools/research_v3/experiment.py --stage validate',
        'OPENBLAS_NUM_THREADS=1 python tools/research_v3/report.py',
        'python -m unittest discover -s research/tests -v','deactivate','```','',
        'report.py экспортирует выбранный launch-default, только когда eligibility и convergence пройдены. Сохраняйте исходные результаты до нового запуска. Для итоговой сдачи нужен отдельный, явно разрешённый финальный test, не автоматический повтор при каждой гипотезе.','',
        'Все JSON, CSV, модели, immutable split и source SHA256 находятся рядом. CI проверяет запуск стандартного launch-default в ROS Humble, включая offline-окружение.','',
        'Метод оптимизации: SciPy least_squares с bounds и soft_l1: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html. Принцип группового разделения: https://scikit-learn.org/stable/modules/cross_validation.html. Эти источники описывают методы, а не результаты нашего эксперимента.']
    (REPORTS/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('EXPORTED',winner,'bootstrap',interval)

if __name__=='__main__':main()
