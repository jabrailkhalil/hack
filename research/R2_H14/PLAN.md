# R2-v7-fixed / H14 — предварительная фиксация

Baseline: `65bba39ed05c781f3f69a65c02f69931152cbfd9`, GuardedReadoutObserver, guarded_readout_v7.yaml; output Estimate.v/s, 20 Hz, alignment_delay_s=0, readout gain=1 / holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau_s=0.5. Ветка research/round2-H14. Main и H11/v8 не включаются. План коммитится до первого исполнения кандидата или анализа development. Исторические validation числа не заменяют исполнение baseline.

## Механизм / ровно ОДИН вариант

H14_async_pairs: отдельный буфер только для adaptation, максимум один новый ACCEPTED sample front и rear. Scalar velocity correction, R/covariance, recovery, stop, readout, физика, Timeline, сетка, matching и единицы не меняются. В core только выделить прежний блок adaptation в переопределяемый метод, baseline body сохраняется. Кандидат наследует GuardedReadoutObserver. Feature off делегирует исходной формуле и побитово воспроизводит R2, включая возвращаемые Estimate/statuses/counters.

Новая пара образуется без ожидания будущего сообщения, по уникальным уже принятым samples. При завершении повторно проверить возраст <=max_age_s, skew <=pair_skew_s, agreement <=disagreement_mps, диапазон скоростей и model innovation gate относительно текущего prediction. Вся пара потребляется один раз, вне зависимости от того, допустим ли ее derivative для обучения. Timestamp пары = (t_front+t_rear)/2 строго возрастает; он не является временем доступности: обучение происходит только в output tick, когда оба сообщения уже доступны. Новая пара НИКОГДА не корректирует v или P второй раз. При FUSED новые samples имеют приоритет над старым pending; синхронный поток должен точно повторять исходное обучение без двойного обновления.

Hard rejection (включая RATE/MODEL/ZERO_LOCK/RANGE/AMBIGUOUS/MISSING_OR_STALE), invalid command, reset и разрыв истории очищают pending и предыдущую adaptation-пару. DUPLICATE_OR_OLD не приносит новых данных. Pending старше max_age_s удаляется; история derivative не старше max_age_s. Сохранить исходный derivative (z-old.z)/(t_pair-old.t), интервал [0.05,max_age_s], abs(a)<=max_accel_mps2, abs(z)>0.5, desired=a-drive_a+resistance(v), weight=1-exp(-dt/adaptation_tau_s), clip disturbance в прежних пределах. H13/integral observer не включать. Никаких новых численных тюнинговых параметров. Diagnostic counters имеют фиксированное число ключей; сырые трассы собирает только offline driver.

Допущение: ACCEPTED при двух моментах плюс повторный общий gate дают пригодную псевдоразметку ускорения. Это НЕ независимость колес и НЕ защита от произвольной согласованной ошибки. Асинхронное усреднение не является временным переносом измерения.

## Предыдущие работы

Прочитать core/guarded_readout/Timeline/config/evaluator/roles/tests на фиксированном SHA, v6 отрицательные результаты; PR14/23 canonical v7, PR26/H11 соседний quarantine (не переносить). H03 (derivative), H04 (tau), H02 (age/skew), H10 (joint observer), H06 (нулевое recovery coverage) изучаются как прошлые кандидаты относительно старого baseline, не как R2 baseline. Existing bootstrap/recovery pending-pair не является новизной H14. Результаты других R2-агентов не читать для выбора алгоритма.

## Бюджет и порядок

1. Sanity и baseline reproduction тем же factory/driver; независимый исходный GuardedReadoutObserver из fixed SHA, параметры parsed из canonical YAML. Проверить effective config/entrypoint. Использовать неизменные score/replay/matching/aggregate с подстановкой Observer factory; historical source pins не переписывать, новый manifest.
2. Feature-off equality, synchronous-stream equality, prefix causality, duplicate/future/stale/reset/gap/range/NaN/bounded-memory tests. Проверить отсутствие второй velocity/P correction на завершающем tick при одинаковом входном состоянии. Контаминированный pending не должен пережить hard rejection. Сохранить все failures/исправления реализации; нельзя превращать исправление в новый tuned вариант.
3. Train smoke: первые 180 s первого lexicographic train bag штатным Store.load(train), vehicle only; без GNSS, без fit и без accuracy claims. Сохранить access.
4. Development: ВСЕ bags настоящей development роли frozen split_v3. Найти существующий read-only development loader; если его контракт не позволяет использование, добавить изолированный role-checked read-only adapter с теми же decoding/scaling/query/matching, не переименовывая роли. Только external evaluator читает разрешенные GNSS. Один заранее заданный вариант + canonical baseline + off ablation, без поиска/fit.
5. Достаточное натуральное покрытие ДО validation: >=100 принятых асинхронных adaptation-пар, >=50 фактических derivative/EMA updates из таких пар, >=2 исходных development groups с такими обновлениями; >=5 s healthy времени вне FUSED суммарно. Показать counts/fraction и длительность. Все условия должны пройти. При недостатке покрытия: INCONCLUSIVE, validation не открывать. Синтетический offset не заменяет эти условия.
6. Development safety gate: обязательные unit/safety probes пройдены, нет новых per-case false stops/unrecovered/coverage loss/resets/causal errors. Если нарушение подтверждено — REJECTED, validation не запускать. Также для этого единственного варианта заранее применить полный общий численный контракт к development: при его непрохождении сохранить REJECTED candidate без расходования validation (не обобщать на весь класс методов). Никакого выбора хороших bags.
7. Если coverage+safety+development admission пройдены, выбрать единственный кандидат и ОТДЕЛЬНЫМ freeze commit опубликовать measured source SHA и SHA256 runtime/patch/config/driver/evaluator/split/данных. Только затем один paired validation на всех штатных validation bags с прежними 4 сценариями. При инфраструктурной ошибке разрешен идентичный rerun в новой директории с описанием причины. После validation ни параметры, ни алгоритм не менять.
8. Final/test DB payloads никогда не открывать. Существующие historical integrity tests могут проверять опубликованные манифесты/архив, но не переоценивать final test.

## Неизменный общий контракт

Clean group-macro RMSE gain >=2% ИЛИ original fault-event group-macro RMSE gain >=5%. Clean, fault-event и pooled RMSE regression <=0.5%; scalar-span distance aggregate regression <=1%; clean per-bag/per-receiver <=baseline+max(0.005 m/s,0.05*baseline). Без потери coverage, новых per-case false stops/unrecovered, нарушений причинности/неожиданных resets. Missing reference=null, не zero. При baseline=0 допускается только candidate<=baseline+1e-12 (абсолютная numerical tolerance); нулевая база не дает relative gain. Legacy decide не менять: недостающие проверки в отдельном research driver.

Показать также MAE, signed bias, recovery_s и локальные регрессии по исходным группам. Два receiver не независимые поездки. Описательный bootstrap не обязателен; не строить CI по независимым ticks.

## Зарегистрированные отдельные диагностики

A. Полный Observer/Timeline, source-time vs availability: 20 Hz output, 10 Hz wheels; synchronous и alternating source offsets 0.05 s; arrivals не раньше source stamps. Healthy ramp/coast/brake/startup, dropout обоих колес [8,13) s после healthy, один spike +5 m/s, чередующиеся zeros, общий zero-lock, rate anomaly до завершения pending, freshness/skew boundaries. Результаты синтетики не входят в admission.
B. Natural development timestamps основной тест. Для каждого development bag отдельная availability-phase диагностика: rear sample time НЕ менять, availability rear +=0.05 s только offline; сравнить baseline/candidate на этом одном заранее фиксированном сдвиге, не ждать будущих сообщений. Если faithful driver недоступен, эту часть отметить NOT RUN, не выдавать подмену source stamps за arrival test.
C. Original faults точно из published evaluator: anchor по vehicle grid; front bias +5 m/s 5 s, both dropout 5/10 s, zero-lock 3 s; окна/masks/aggregation без изменений. Дополнительные suites не подменяют эти faults.
D. На первом lexicographic development bag после warmup 10 s использовать тот же последующий 180 s поток. 3 AB/BA пары (6 упорядоченных пар, 12 replays), OPENBLAS/OMP=1, одинаковый сбор Estimate. Отдельно wall, process CPU, wrapped step CPU и peak RSS; observer cost не называть installed ROS latency. Если accuracy отклонена — полный installed ROS benchmark не выполнять и указать это. При accuracy pass нужен включенный candidate в offline ROS 2 CPU/500000000 bytes и обоих clock modes.

## Научные проверки

Consensus narrow search; Scite metadata/abstract/citation context по 1-3 релевантным первичным работам, явно уровень прочитанного. Wolfram worksheet: среднее timestamp при affine v(t), bounded pair monotonicity/uniqueness invariant, произведение exp(-dt/tau)=exp(-sum(dt)/tau), learning weight для двух подшагов без повторения, correlated wheel noise variance (не 1/N), disturbance clip bounded. Math в идеальной модели не доказывает эмпирический выигрыш. Сохранить фактический tool output; недоступность не выдумывать.

## Команды / evidence

Проектируемые точки запуска (точные опции фиксируются вместе с кодом до исполнения):

```bash
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
git apply --check research/R2_H14/adaptation-hook.patch
git apply research/R2_H14/adaptation-hook.patch
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2_H14/tests -v
python tools/get_dataset.py
python tools/research_R2_H14/run.py --stage development --output "$OUT"
# Следующая команда разрешена только после gates и отдельного freeze commit:
python tools/research_R2_H14/run.py --stage validation --freeze "$FREEZE" --output "$NEW_OUT"
```

Каждый output новый. Research workflows только в данной ветке, evidence в `checkpoint/R2-H14-<run_id>-<attempt>` / `reports/research_R2/H14/<run_id>-<attempt>/`; raw bags/секреты/кэши не коммитить. Source snapshot workflow без measurements допустим для переноса кода в execution container (локальный git clone недоступен из-за DNS); результаты исполнения будут честно разделены local/Actions. Итоговый русский REPORT+draft PR: CONFIRMED/REJECTED/INCONCLUSIVE, отдельно mechanism coverage и merge readiness. Никаких merge/auto-merge/force-push/main edits.
