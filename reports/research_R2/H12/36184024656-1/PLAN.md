# H12 / R2-v7-fixed — PLAN до исполнения

Baseline: 65bba39ed05c781f3f69a65c02f69931152cbfd9. Canonical GuardedReadoutObserver, guarded_readout_v7.yaml, odometry.launch.py / guarded_odometry_node; 20 Hz, alignment_delay=0, readout gain=1, holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau=0.5. Не использовать moving main/H11/v8. Ветка research/round2-H12 создана от этого SHA; main/чужие ветки не изменяются. Merge и auto-merge запрещены.

## Механизм и единственный вариант

Ровно один кандидат H12_piecewise_integral; подбора параметров нет. Только readout: заменить a_model(t)*mean(age) средним индивидуальных интегралов истории pre-correction model acceleration на [sample.t,t]. Сегменты (old_t,t] содержат ускорение, действительно использованное исходным Euler predictor: drive уже обновлён в конце шага, resistance вычислено от old_v, disturbance от начала шага. Это дискретная модельная реконструкция, не истинное прошлое ускорение. Не использовать a_output, скачки Kalman correction, GNSS/IMU, bag IDs, fault oracle или future samples. История deque maxlen=16; удалить интервалы, полностью старше max_age_s, оставляя пересекающий границу сегмент. Если хотя бы один принятый sample не покрыт, весь update использует точную старую формулу. gain, holdoff, clip/sign/zero-lock guards, core, covariance, disturbance, Timeline и физика не меняются. Поправка не подаётся внутрь. Off абляция выключает ТОЛЬКО интегральную замену, не весь v7 readout.

Отличие от H08 (#25): numerical predictor/core не меняется. От H01 (#21), v6 projection/decay и H02 (#15): нет изменения внутренних измерений, R или адаптации. PR #14/#23 задают исходный output-only v7; H11/#26 — соседняя common-mode quarantine и не входит в H12.

## Источники и аналитика

Прочитать относящиеся к теме исходники/PR и роли данных. Узкий Consensus поиск, Scite metadata/доступный текст/контекст; 1–5 источников, явно различать abstract/fragments/fulltext. Не переносить другие sensor interfaces. Wolfram worksheet: affine acceleration endpoint error j*h^2/2, right-endpoint quadrature и partial-cell error, h->0, constant acceleration, mean individual integrals против mean stamp, bounded correction recursion и единицы. Аналитика не доказывает accuracy.

## Порядок и роли данных

До первого эксперимента коммитится этот PLAN. Сначала structural/unit tests и baseline reproduction на development: исходные ev.score/replay и отдельный canonical guarded driver должны дать те же опубликованные Estimate.v/s и counters на одних событиях. Не читать старые final/test results как кандидат. Исторические hashes/guards не переписывать.

Train: первые <=180 s всех 64 штатных train bags, только controller/front/rear, без GNSS labels. Проверки finite, schedule, prefix causality, state identity; не подбор accuracy.

Development: все 17 bags настоящей роли development. Read-only loader проверяет роль и checksum ДО SQLite IO, reference только внешний evaluator. Полный clean и исходный fault suite для baseline и единственного candidate, original score/match/distance/aggregation. Не выбирать bags по ошибке. Источники и данные фиксируются отдельным актуальным manifest, старые pins не менять.

До validation обязательны safety/coverage: все unit/identity/prefix/reset/future/stale/duplicate checks; на всех replay ticks побитовая идентичность ВСЕХ core state fields, исключая только published last_estimate и собственные readout-state fields. Off дополнительно совпадает по всем v7 readout fields/Estimate/counters, добавленная отключённая история пуста. Проверить саму историю против независимо захваченного pre-correction acceleration.

Достаточная естественная активация: >=1000 eligible readout updates с |mean_integral-a_current*mean_age|>1e-9 m/s, >=3 development groups с такими изменениями, >=100 таких updates в окне [controller change, change+2 s]. Controller transition: изменение знака режима (traction u>.04, coast |u|<=.04, brake u<-.04), либо |delta u|>=.1; не чаще одного anchor за 5 s. Дополнительно показать долю активации, age/skew bins, fallback/multisegment, max delta. Если недостаточно — INCONCLUSIVE по механизму/общему исследованию, validation НЕ открывать. Если safety провален — REJECTED. Эффект одного текущего сегмента (математически совпадает со старой формулой) и округление не считать активацией. Порог не снижать после результатов.

Если coverage/safety достаточны и development nonregression guards ниже выполнены, заморозить единственного кандидата. Minimum efficacy на development не обязателен; это не второй кандидат. Создать и опубликовать отдельный FREEZE commit (candidate source SHA, code/config/evaluator/driver/manifest/split/data hashes) ДО validation. Затем один paired validation всех 19 bags и исходных faults. Никакой перенастройки после validation. Повтор только того же freeze при инфраструктурном сбое/для воспроизводимости, с новым run ID. Final/test measurement payloads не открывать.

## Неизменный общий контракт

Clean group-macro RMSE gain >=2% ИЛИ original fault-event group-macro RMSE gain >=5% против R2 v7. Дополнительно clean/fault/pooled regression <=0.5%; scalar-span distance aggregate regression <=1%; clean per-bag/per-receiver <=base+max(.005 m/s,.05*base). No coverage loss, extra false-stop samples in any comparison, new unrecovered cases in any comparison, causal errors or unexpected resets. Baseline=0: candidate должен быть <=1e-12 абсолютной ошибки, gain не начислять; missing metric не равна 0, при недостатке reference INCONCLUSIVE. Legacy decide дополняется отдельными строгими guards, не меняя измеритель. Те же nonregression guards используются на development, но gain gate только на validation.

Показать MAE, signed bias, p95, recovery time, локальные clean/fault/distance регрессии. Агрегировать по исходным группам; receivers не независимые поездки. Bootstrap не требуется.

## Заранее заданные диагностики

1. На реальном development clean: переходные окна [anchor,anchor+2 s], та же reference mask, отдельные phase metrics. До/во время/после original faults trace. Age bins <=.05, (.05,.1], >.1; skew <=.025 и >.025.
2. На первых подходящих переходах каждого development bag (t>25, t<end-15, valid wheels speed>0.4), максимум 3 anchors/bag, injected both-wheel dropout 1 s одновременно с переходом. Anchor только vehicle, warmup 20 s/recovery 10.1 s. ОТДЕЛЬНАЯ diagnostic suite, не подмена original admission.
3. Synthetic direct step: постоянное/изменяющееся acceleration, переменные ages .02/.08/.15/.24 и skew 0/.04/.09, piecewise crossings, insufficient coverage, >16 tiny intervals, command transitions, simultaneous dropout, stop/zero-lock, reset. Не выдавать за реальные accuracy.

## Стоимость, CI, артефакты

На лексикографически первом development bag — первые 70 s, 10 s warmup; 6 paired AB/BA repeat (порядок чередуется), одинаковые outputs, threads=1. Разделять step CPU/wall и replay CPU/wall; без дорогой identity instrumentation в timed path. RSS process high-water отдельно, не называть per-model peak разницей rss cumulative. Сохранять raw timings, не делать hard real-time выводов.

При accuracy PASS нужен свежий installed enabled H12 ROS offline 2 CPU/500000000 bytes, оба clock modes, реальный development replay. При rejected accuracy или недостаточной активации полный ROS benchmark можно пропустить с явной отметкой. Сборку и доступные baseline tests не выдавать за enabled ROS. Статус обычного CI проверять отдельно; красные historical guards не удалять.

Команды (измеренная реализация будет закреплена следующим отдельным commit):
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R2/H12/test_h12.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research/R2/H12/run.py --stage development --output /tmp/H12-new-run
# run.py выполняет train sanity, весь development, diagnostics, cost и prevalidation decision.
python research/R2/H12/run.py --stage freeze --output /tmp/H12-new-run
# Публикация freeze commit ДО validation, только при разрешении prevalidation decision.
python research/R2/H12/run.py --stage validation --output /tmp/H12-new-run

Reports: reports/research_R2/H12/<run-id>/, checkpoints только checkpoint/R2-H12-<run-id>-<attempt>. PLAN/freeze/report/patch/config/code, sources/worksheet, фактические команды/логи, raw JSON/CSV, access journal. Raw bags/secrets/cache не коммитить. Draft PR русский, CONFIRMED/REJECTED/INCONCLUSIVE + отдельные mechanism/merge statuses; без подмены missing execution выдуманными результатами.
