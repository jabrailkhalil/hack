# H19 / R2-v7-fixed — предварительный план

Статус: до первого H19 replay, теста и просмотра H19 метрик. Подготовительный source-export не открывал измерения. Ветка research/round2-H19 создана от 65bba39ed05c781f3f69a65c02f69931152cbfd9. Merge/auto-merge/изменение main запрещены.

## Baseline и предшествующие работы

Единственный baseline: 65bba39ed05c781f3f69a65c02f69931152cbfd9, GuardedReadoutObserver, guarded_readout_v7.yaml/json. Эффективные readout gain=1, holdoff_s=0.5, inner wheel_time_compensation=0, adaptation_tau_s=0.5; 20 Hz, delay=0. Сравниваются возвращённые Estimate.v/s, не inner v/s. Сохраняются low-speed ZERO_LOCK_SUSPECT, bootstrap, hard gates, stop, reacquisition, физика, Timeline и исходные единицы.

Изучены core, guarded_readout, Timeline, конфигурации, evaluator/score/match и роли данных; v6 REPORT, относящиеся H02/#15, H05/#17, H09/#24 и успешные #14/#23. H05 накапливал уже зарегистрированные аномалии и не достиг minimum gain; H19 использует subthreshold innovations, а также запрещает загрязнение disturbance подозрительной парой. #26/H11 блокирует reacquisition после резкого общего RATE_ANOMALY; его код/параметры НЕ включаются. Старые метрики не являются R2 baseline measurements.

## Механизм и фиксированный бюджет

Ровно ДВА варианта одного алгоритма: h03 (H=0.30 s) и h06 (H=0.60 s). Остальные параметры одинаковы и не подбираются: tau=2.0 s, Cmax=2.0 s, kappa=0.25, clip=3.0, release=H/4, q_suspect=0.25, positive-evidence TTL=4.0 s. Baseline/off/monitor-only — проверки, не дополнительные подбираемые варианты. После development не расширять бюджет.

На каждом новом прошедшем исходные hard gates sample i используется последнее свежее прошедшее gates измерение другого колеса j. Peer может быть held, но это не новая ассимиляция. Ни future, ни rejected peers не используются. Skew <= existing pair_skew_s; при stale command/peer, общей неоднозначности или малой скорости <=0.5 m/s действие отключено. Детектор не меняет sample values/stamps и не ожидает пару.

До wheel correction: r_i=(z_i-v_pred)/sqrt(P_prior+sigma_w^2+Q_v*age_i), аналогично r_j; d_i=(z_i-z_j)/sqrt(2*sigma_w^2+(a_max*abs(t_i-t_j))^2). Нормировка фиксированная/из prior baseline, не обучается на текущем выбросе.

Односторонняя атрибуция i разрешена только при abs(r_i)>=abs(r_j)+0.5, abs(r_j)<=1, r_i*d_i>0, abs(d_i)>0.5 и обеих свежих скоростях >0.5 m/s по модулю. Иначе evidence e_i=0. При разрешении e_i=sign(r_i)*min(abs(r_i),abs(d_i),3). Два колеса не объявляются независимыми датчиками; модель НЕ считается истиной. При отсутствии однозначности q=(1,1).

Двусторонняя рекурсия для каждого канала:
C_i^+ = clip(exp(-dt_i/tau)*C_i^+ + dt_i*(e_i-kappa),0,Cmax)
C_i^- = clip(exp(-dt_i/tau)*C_i^- + dt_i*(-e_i-kappa),0,Cmax).
Детекторное dt_i — source-stamp interval между различными обработанными samples; первый sample и дубликат дают 0 evidence-time; gap>max_age сбрасывает, не начисляет свидетельства за пропуск. Prediction ticks только забывают/проверяют сроки. Состояние ограничено четырьмя C, двумя peer samples, timestamps/флагами/диагностическими скалярами; O(1), TTL истории <=4 s. Reset очищает всё.

Latch появляется при max(C)>=H, снимается при max(C)<=H/4 или отсутствии положительного evidence 4 s. Уменьшение веса применяется только для ОДНОГО подозрительного канала при текущей односторонней атрибуции и валидном peer; на ambiguity применяется baseline fallback. Принятый z становится sum(q_i*z_i)/sum(q_i), R умножается на len(accepted)/sum(q_i), без R/N. При q=(1,1) сохраняется исходная арифметика. Подозрительный принятый канал получает отдельный status, который естественно блокирует existing guarded readout. FUSED disturbance adaptation запрещена при активном downweight, adapt_previous очищается. Сам readout не переписывается. Hard reject, reacquisition и остановка не ускоряются.

## Данные, последовательность и достаточность

1. Sanity и canonical baseline reproduction: независимый pristine v7 из Git object и baseline того же driver сравниваются потактово на всех development/original fault cases. Off дополнительно совпадает по Estimate, статусам, счётчикам и полям baseline state. Никакие исторические результаты не подставляются вместо исполнения.
2. Train: первые <=180 source seconds всех 64 train bags; только три vehicle topics, штатный Store.load(train). Без fit/GNSS; execution/off/prefix/finite проверки, не точность.
3. Development: все 17 development bags/все их группы, отдельный read-only loader с role check до SQLite IO и checksum каждого bag. Допустим локальный проверенный development-export H09 run 36174399106 (архив SHA256 5a840289a44b90d118847b33cdab2d3820ede3d92678bef350ed475f40c47fce), только после проверки export hashes/role/bag hashes по R2 split. Его OLD core не используется. Обязательный remote повтор напрямую из SQLite. Не использовать validation других R2 агентов.
4. До validation: минимум 100 weighted accepted updates суммарно на >=3 development группах и минимум 10 диагностических инъекций с обнаружением; отсутствие увеличения false stops/unrecovered, пер-timestamp coverage loss и NaN/causal/reset нарушений; clean alarm budget ниже. Если механизм неактивен — INCONCLUSIVE/coverage, не опровержение семейства. Если активен и контракт не пройден — REJECTED конкретных вариантов.
5. В validation проходит только вариант, прошедший ПОЛНЫЙ общий контракт также на development и safety/coverage gate. Из прошедших: минимальный original fault macro RMSE, затем clean macro, затем более высокий H. Специальная suite не используется для замены main gain. При отсутствии прошедшего варианта STOP: validation не открывать. Один прошедший candidate публикуется отдельным freeze commit с SHA/hashes до единственного paired validation. После validation параметры не менять.
6. Final/test payloads не открывать и не пересчитывать. Download/unpack архива не даёт разрешения SQLite IO test. Reused validation не independent final test.

## Неизменный измеритель и контракт

Новый изолированный driver/factory, старые evaluator и pins не редактировать. tools/finalization/evaluate.py score/replay/distance, research_v3 match/metrics, research_v6 group-macro summary и исходное fault placement остаются побайтно baseline. Driver подставляет только Observer. Значения/маски/сетка общие для обоих алгоритмов. Отдельный текущий manifest фиксирует evaluator/driver/split/config/source hashes.

Clean group-macro RMSE gain >=2% ИЛИ ORIGINAL fault-event group-macro RMSE gain >=5%; clean/fault/pooled regression <=0.5%; scalar-span distance aggregate <=1%; clean per-bag/per-receiver <=baseline+max(0.005 m/s,5% baseline). Без loss coverage, дополнительных false stops, новых unrecovered cases, causal errors/unexpected resets. Если baseline=0: допустима только абсолютная delta<=0; missing reference !=0. Проверять missingness, per-case false stops/recovery, MAE, signed bias, p95, recovery time и регрессии. Receiver-wise counts не независимые поездки.

Original faults неизменны: front+5m/s 5s, both dropout 5/10s, both lock3s; anchor — первый vehicle grid point valid, average wheel speed>2, t>max(25,0.1*t_end), t<t_end-25; окно [anchor-20,anchor+duration+10.1].

## Отдельная H19 diagnostic suite (не admission)

На ТЕХ ЖЕ vehicle-only anchors и на всех bags, где anchor существует. Для каждого колеса и обоих знаков:
- gradual drift: линейный рост 0 -> +/-0.4 m/s за 4s, затем удержание ещё 4s; fault duration 8s;
- intermittent offset +/-0.2 m/s, period=0.5s, duty=0.5, duration=8s.
Итого 8 cases/bag. Никакого выбора anchors по GNSS/error. Fault metadata остаётся только в offline injector/evaluator и никогда не передаётся Observer. Score вызывается на предварительно изменённом событийном массиве с diagnostic marker, который не включает original injector повторно; все формулы/маски/aggregation неизменны.

Диагностика: weighted updates/duty, time of detection, wrong-channel weighted updates, clean alarm episodes/rate, disturbance change относительно clean twin (прокси contamination, не true disturbance), recovery time, режимы before/during/after. Естественный clean не имеет независимых fault labels: ВСЕ срабатывания на нём консервативно считаются false-alarm proxy. Budget: weighted duty <=0.5% всех выходов aggregate и <=1% каждой группы; alarm onsets <=2/min aggregate; no growth false stops; дополнительно не увеличивать STOPPED при reference 0.07..0.5 m/s. В diagnostic injections wrong-channel weighted updates во время fault должны быть 0; отсутствие атрибуции отдельно отмечать, не считать правильным обнаружением.

Ablation: off на реальных streams; monitor-only synthetic проверяет, что одни C не меняют baseline; изолированные deterministic tests для weighted fusion и adaptation freeze/release. Не подбирать дополнительные composite variants.

## Проверки, стоимость, публикация

Unit/integrity: duplicate/held/future/stale/reset, arbitrary prefix extension, bounded state/time TTL, no NaN, asymmetric bias, ambiguous pair/common-mode, true stop/zero lock, no accelerated reacquisition, disabled exact equality. Sanity failures сохранять, инфраструктурное исправление отличать от смены гипотезы.

Стоимость: первые 180 s первого development-bag после 10 s warmup, три AB/BA пары, одинаковые outputs, OPENBLAS/OMP=1. Отдельно replay CPU/wall, step CPU и process RSS; не выдавать это за ROS latency. При выполненном accuracy-gate свежая installed ENABLED candidate ROS offline 2 CPU/500000000 bytes, оба clock modes и real development replay обязательны. При REJECTED полный ROS benchmark можно не выполнять, явно записав это.

Источники: 1–5 работ. Consensus узкий поиск; Scite фактическая попытка 25.09.2026 вернула monthly 25-call quota, reset 01.10.2026 — тексты и smart citations этим сервисом в H19 НЕ прочитаны. Платные действия запрещены. Wiley fulltext также может быть недоступен; различать metadata/abstract/fulltext. Wolfram worksheet сохраняет реальный результат, предупреждения и исправленный расчёт; не переносить идеальные гарантии CUSUM/PFEKF в нелинейную коррелированную одометрию.

Команды (из полного checkout, новые output dirs):
```bash
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R2/H19 -p 'test_*.py' -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/research_h19/run.py --stage train --output /tmp/H19-train-new
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/research_h19/run.py --stage development --output /tmp/H19-dev-new
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/research_h19/run.py --stage benchmark --output /tmp/H19-benchmark-new
# validation только при опубликованном разрешающем freeze и пройденном dev gate:
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/research_h19/run.py --stage validation --freeze research/R2/H19/FREEZE.json --output /tmp/H19-validation-new
```

Артефакты: research/R2/H19, reports/research_R2/H19/<run-id>/; отдельные run_id/attempt checkpoint branches. Сохранить полный metrics JSON/per-bag/per-receiver/per-fault CSV, raw output traces разумного размера, access/commands/tests/manifest, patch/source, sources и worksheet. Не коммитить raw bags, secrets/caches и не изменять опубликованные отчёты. Итоговый draft PR на русском: CONFIRMED/REJECTED/INCONCLUSIVE, точный baseline/measured/report SHA, ограничения. REJECTED/INCONCLUSIVE явно: исследовательский артефакт, не готов к merge.
