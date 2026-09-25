# H10 — совместный observer скорости и возмущения

Исследовательский кандидат; этот каталог **не переключает default**. Для эксперимента применяется `algorithm.patch`. Даже после применения H10 включается только через `joint_observer_enabled=1`; disabled-path воспроизводит baseline. Не применять как подтверждённое улучшение до чтения фактического отчёта.

Baseline: `984fdf2fc4faf05325249215d6b8541c0e68209a`, `adaptive_v5`. План до реализации и экспериментов: commit `50515d4924cf0275ef071c8af38bd6cf0b6810d6`. Единственный вариант: `H10_joint_q004`, qd=0.04; параметрический поиск не проводился. Измеряемая реализация: `867ff876284a50355d855273c214769e2356a4ae`.

## Отличия от baseline

Состояние `[v,d]`, симметричная ковариация `P=[[Pvv,Pvd],[Pvd,Pdd]]`. Средний прогноз привода, сопротивление, timestamps, gates и Timeline сохранены.

Для локального якобиана `F=[[f,dt],[0,1]]` (с учётом насыщения/проекции) применяется `P-=F P F^T+Q`, где disturbance random walk добавляет `qd * [[dt^3/3,dt^2/2],[dt^2/2,dt]]`, а прежний velocity process noise — в `Qvv`. f включает производную текущего drive target и сопротивления; uncertainty истории actuator не включена в состояние, поэтому это приближённая covariance, не точный posterior.

Измерение `H=[1,0]`. R остаётся исходным robust R: согласованные колёса не объявляются независимыми. При доверенной паре `K=[Pvv,Pvd]^T/(Pvv+R)`. Обе компоненты среднего корректируются одной innovation. Во всех остальных случаях `Kd=0`, но применяется **полная Joseph-форма** `(I-KH)P(I-KH)^T+KRK^T`; uncertainty d не уменьшается как будто неисправный канал наблюдал disturbance. Прежние условия допустимости адаптации (две новые согласованные/model-consistent скорости, свежий controller, допустимые pair-dt/ускорение/минимальная скорость) сохранены.

Сохраняются ограничения v/d, нули при подтверждённой остановке, bounded reacquisition, запрет zero-lock-stop на существенной модельной скорости. P ограничивается PSD-preserving диагональным масштабированием; после проекции d cross-covariance обнуляется. При пропадании данных среднее d удерживается, а не затухает, в отличие от отвергнутого v6.

## Запуск точной реализации

В отдельной рабочей копии (не в рабочем main):

```bash
git fetch origin research/parallel-H10
git worktree add --detach ../hack-H10 867ff876284a50355d855273c214769e2356a4ae
cd ../hack-H10
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-research.txt

export H10_BASELINE_CORE="$(mktemp /tmp/H10-baseline-XXXXXX.py)"
git show 984fdf2fc4faf05325249215d6b8541c0e68209a:src/reserve_odometry/reserve_odometry/core.py > "$H10_BASELINE_CORE"
git apply --check research/parallel/H10/algorithm.patch
git apply research/parallel/H10/algorithm.patch
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p test_core.py -v
python research/parallel/H10/test_joint.py
python tools/get_dataset.py

OUT="$(mktemp -d /tmp/H10-results-XXXXXX)"
python research/parallel/H10/run.py --stage train --output "$OUT/train"
python research/parallel/H10/run.py --stage freeze --training "$OUT/train" --output "$OUT/FREEZE.json"
python research/parallel/H10/run.py --stage validation --freeze "$OUT/FREEZE.json" --output "$OUT/validation" --workers 2
```

Первое измерение выполняется workflow `H10 joint observer paired research`, run `36175232852`. Повтор неизменного кандидата для воспроизводимости не является независимым test. Не подбирать новый qd по этим validation-результатам в рамках H10.

## Неизменный измеритель и данные

`run.py` импортирует baseline `tools/finalization/evaluate.py` и `tools/research_v6/compare.py`. Меняется только фабрика Config. Их scoring, timestamps, reference matching/masks, fault construction, aggregation и исходные acceptance checks не редактируются. Файлы evaluator, Timeline, frozen split и активного профиля проверяются against git baseline перед train, freeze и validation.

Train читает только controller/front/rear через исходный `Store.load(...,'train')`. GNSS-reference на train не читается и train accuracy не заявляется. Validation выполняется только после FREEZE.json и проверки source/config/evaluator hashes. Исторический final test не вызывается, его цифры к H10 не относятся.

Порог: ≥2% clean либо ≥5% fault RMSE gain; ≤0.5% регрессии основных агрегатов, ≤1% distance, per-bag ≤max(0.005 м/с,5%); no extra false stops/unrecovered faults, no loss of coverage, no causality/reset regressions. Письменный лимит 0.5% также проверяется для pooled RMSE, не ослабляя исходный v6 `decide()`.

## Артефакты

Каждый GitHub run/attempt имеет отдельную ветку `checkpoint/research-H10-<run_id>-<run_attempt>` и директорию `reports/research_parallel/H10/runs/<run_id>-<run_attempt>`: `PLAN.json`, `READY.json`, `FREEZE.json`, train raw JSON/per-bag timing, validation raw `results.json`, `decision.json`, `comparison.csv`, `bags/*.json`, `access.json`, `REPORT.md`, логи тестов/датасета/стадий. Старые отчёты не перезаписываются; отрицательные результаты сохраняются.

## Границы доказательств

Локально выполнены 20 implementation tests, включая exact disabled-baseline equivalence на 6000 шагах и PSD/state/memory invariants на 15000 шагах. Это не real-data accuracy. Train wall_us_per_output включает offline Timeline/replay/сбор массива и не является ROS latency. Этот workflow не выполняет полный ROS publisher-to-subscriber benchmark H10 на 2 CPU/500 MB. Validation повторно используемый, не независимый final test; distance — переякоренный скалярный surrogate, не xyz. Произвольная согласованная ошибка обоих колёс без независимого источника не устраняется.
