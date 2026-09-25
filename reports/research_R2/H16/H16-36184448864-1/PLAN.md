# H16 / R2-v7-fixed — PLAN до экспериментов

Baseline: `65bba39ed05c781f3f69a65c02f69931152cbfd9`. Ветка `research/round2-H16`. Реальный baseline — GuardedReadoutObserver, guarded_readout_v7.yaml/json, gain=1, holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau=0.5, Timeline 20 Hz / delay 0. Не включать H11/v8. Сравнивать возвращаемый Estimate, не внутренние v/s.

## Гипотеза и границы

Изменить только калибровку семи существующих эффективных физических параметров. Сохранить physical structure, legacy update drive-before-Euler, сопротивление, ограничения, disturbance adaptation, R/gates, zero-lock, readout, Timeline и единицы. Runtime-патч — отдельный измеренный JSON/YAML; основной код/default не меняются. Выключение H16 означает точный исходный v7 профиль, НЕ readout.gain=0.

H03 (#20) улучшил wheel-derived acceleration/roughness proxy, но ухудшил fault accuracy. H07 (#22) изменял tau по режимам и также не прошёл accuracy gate. H16 не добавляет такую асимметрию, сглаживание, projection/decay v6, новую адаптацию или механизм H11. PR #14/#23 задают baseline readout и zero-lock.

## Ровно два train-варианта

Порядок theta: force_per_mass [m/s²], power_per_mass [m²/s³], brake_per_mass [m/s²], rolling_per_mass [m/s²], quadratic_per_mass [1/m], command_exponent [1], actuator_tau_s [s].

Bounds как v3: LOW=[0.05,1,0.05,0,0,0.3,0.05], HIGH=[5,100,5,0.4,0.005,3,3]. Масса/радиус/КПД/передача и масштабы датчиков не подбираются. theta0 из действующей v7 калибровки.

(A) robust multi-horizon simulation loss. (B) тот же loss + регуляризация к theta0. Для каждого ровно один scipy.optimize.least_squares(method=trf, jac=2-point, max_nfev=80, ftol=xtol=gtol=1e-8); без restarts. Считать отдельно фактические вызовы residual: max_nfev не включает численное дифференцирование Jacobian. Начало обоих theta0; x_scale=max(abs(theta0),0.1*(HIGH-LOW)); никаких смен solver/bounds по результатам.

Горизонты H=[0.5,2,5] s. sigma(H)=0.1+0.2*H m/s, то есть [0.2,0.5,1.1] m/s. r=(v_pred-y_wheel)/sigma. rho(r)=2*(sqrt(1+r²)-1). L_A=mean_group(mean_window(mean_horizon(rho(r)))). Равный вес исходных групп, затем окон, затем трёх горизонтов. Реализация через стабильный transformed residual r*sqrt(2/(sqrt(1+r²)+1))*sqrt(weight) и loss=linear, поэтому robust threshold не зависит от размера группы. L_B=L_A+0.01*mean_j(((theta_j-theta0_j)/scale_j)²). Все слагаемые безразмерны.

## Train данные, causal warmup и независимый check по группам

Использовать все 64 train bags, штатный Store.load(train), только controller/front/rear, train GNSS не читать. Из 27 train groups отсортированные по group ID позиции 0,4,8,12,16,20,24 составляют check; остальные fitting. Связанные bags не разделять. Группы check никогда не входят в residual solver.

На исходной Timeline 20 Hz собрать разрешённые held inputs. Предусмотреть по одному окну на каждый command-режим каждого bag: traction u>0.04; braking u<-0.04; coast иначе. Максимум три окна/bag, одинаковые для baseline/A/B. Кандидаты anchors: после 10 s, не менее 5 s до конца, оба fresh/agreeing wheels (difference <=0.15 m/s), positive mean speed 0.5..35 m/s, fresh legal command. Требовать эту vehicle-only маску на всём warmup 5 s и forecast 5 s. В каждой фазе взять средний по времени допустимый anchor, без выбора по ошибке/target GNSS. Недоступные фазы явно считать отсутствующими.

Для КАЖДОЙ theta начальное состояние получается запуском настоящего GuardedReadoutObserver на исходных held inputs за 5 s ДО маскированного окна (до anchor включительно). Ни initial v, ни initial d не являются переменными оптимизации. Predictor внутри окна получает только causal команды и собственные рекурсивные состояния. Wheel targets доступны исключительно loss, не resistance/drive_target. Допускается vectorized offline recurrence, только после проверки численного совпадения с настоящим Observer на model-only rollout; runtime numerical scheme не менять.

Псевдоцель: среднее двух held скоростей на соответствующем исходном output tick горизонта; без GNSS и без переименования её в ground truth. Не подставлять эту скорость в рекурсивную динамику. Forecast horizons >=0.5 s превышают max_age, поэтому output readout уже обнулён после удаления новых wheels. При checked rollout прошлые held колёса могут только стареть, но не заменяться target.

Показать baseline/A/B loss, RMSE/MAE/signed bias по горизонту, фазе, bag, fitting/check группе; theta, solver success/status/nfev/residual calls, active bounds и groupwise стабильность. Дополнительных per-group refits нет. Сильная group dependence: check group-macro 5s RMSE хуже baseline более чем на 25% И на 0.05 m/s; либо более половины check-групп хуже на 20% И 0.05 m/s. Это препятствие продвижению, не доказательство невозможности семейства.

Минимальное покрытие fitting >=8 групп и >=30 окон; check >=3 групп и >=9 окон; в совокупности >=5 окон каждой из трёх фаз. При недостатке INCONCLUSIVE без validation. Не расширять выбор anchors/бюджет после измерений.

## Development и выбор

Вся исходная роль development: 17 bags / 7 групп. Новый read-only role-checked loader с теми же decode/units/receipt order/hash; не изменять старый Store, split или roles. GNSS только снаружи observer. Сравнить baseline и оба варианта одним ev.score, ev.replay и v6.summary; сохранённые source hashes проверяются до работы. Служебные legacy aliases baseline_v2 и balanced_physics означают v7 и исследуемую калибровку, не исторические версии.

Сначала воспроизвести R2 baseline независимым canonical construction vs research factory; сравнить опубликованные массивы, статусы и runtime counters, дополнительно ev.score vs независимый guarded.compare на одинаковом development bag. При расхождении остановиться до сравнения кандидатов. Исторические validation цифры не заменяют исполнение.

Оба варианта получают полный clean и original fault development replay. Не использовать validation других R2 агентов. Дополнительно измерить изменение output/internal dynamics, количество MODEL_ONLY/FUSED/SINGLE_WHEEL/REACQUIRING/STOPPED ticks, время фаз и bounded состояния до/во время/после original faults. Diagnostic traces только логируют, fault flag не поступает estimator.

Для продвижения необходимы solver finite/bounds, достаточное train покрытие, отсутствие сильной group dependence, sanity/safety PASS и development non-regression gates общего контракта (включая per-case stops/unrecovered/coverage), но минимальный gain на development не обязателен. Среди допустимых выбрать минимальный original fault group-macro RMSE; при равенстве clean, затем B. Если ни один не допустим — REJECTED для двух проверенных кандидатов, validation не расходовать. Если механизм неактивен (ни один физический коэффициент не изменился существенно или <100 изменённых published velocity ticks в <3 development группах) — INCONCLUSIVE.

## Общий неизменный R2 admission

Final validation выбранного кандидата: >=2% уменьшения clean group-macro RMSE ИЛИ >=5% уменьшения original fault-event group-macro RMSE относительно v7. Clean/fault/pooled не хуже более 0.5%; scalar-span distance aggregate не хуже более 1%; clean per-bag/receiver <=baseline+max(0.005 m/s,5% baseline). Никакой потери coverage, новых false stops/unrecovered per comparison, причинных ошибок или неожиданных resets. При нулевом baseline допустима только абсолютная положительная погрешность <=1e-12 (n/stops/counters требуют точного равенства); zero baseline не даёт процентного gain.

Original fault placement/warmup/masks/recovery совпадают с v6: first vehicle-valid speed>2 anchor после max(25s,0.1*duration) и до duration-25; front+5m/s bias 5s, both dropout 5/10s, both lock 3s; warmup20s, recovery10s. Никакие дополнительные сценарии не подменяют этот gate.

Дополнительная safety: unit zero-lock на малой скорости, duplicate/future/stale, causal prefix, reset, finite states и hard limits. Нет новых runtime histories и NumPy/SciPy imports. Candidate-off должен повторять ВСЕ outputs/statuses/counters v7. Full historical tests сохраняются даже при красном результате.

## Freeze, validation, performance

Только после выбора: отдельный опубликованный freeze commit с candidate JSON/YAML, SHA всех runtime/config/evaluator/driver/PLAN файлов, training/development results hashes, dataset/split hashes, списком открытых roles. Validation loader требует этот commit и проверяет идентичность хешей. Один selected validation, все19bags/76originalfaults, оба receiver. Final/test SQL payloads закрыты. Reused validation не является independent final test.

Стоимость: один development stream, первые60s для warmup и измерения (первые10s исключаются из step-statistics), три AB/BA пары (шесть ordered pairs), OPENBLAS/OMP=1, одинаковый сбор Estimate. CPU и wall на replay, step p50/p95/p99 отдельно, ru_maxrss отдельно; не называть их установленной ROS latency. Сравнение не используется для смены theta. После accuracy PASS обязательны свежий installed enabled candidate ROS offline 2 CPU/500000000 bytes, оба clock mode на реальном development; без них максимум INCONCLUSIVE. При accuracy REJECTED полный ROS benchmark можно пропустить с явной отметкой.

## Исполнимый маршрут и evidence

research/R2/H16/run.py: `sanity --output DIR`; `train --output DIR`; `develop --train DIR --output DIR`; `freeze --train DIR --development DIR --output DIR`; `validate --freeze FILE --freeze-commit SHA --output DIR --workers 2`; `benchmark --candidate FILE --output DIR`. Новый output обязателен. Train обаobjective за один зарегистрированный stage. Никаких append измерений в опубликованные results.

Перед началом: `python -m pip install -r requirements-research.txt`; `python tools/get_dataset.py`; `export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`. Исходный штатный downloader распаковывает общий архив; отдельный preparation artifact передал локально только train/development, без validation/test. Подготовка/копирование байтов до PLAN не является экспериментом; ни одного replay/fit до этой фиксации не было.

Отчёт reports/research_R2/H16/<run-id>/REPORT.md, raw per-bag/receiver/fault JSON/CSV, access журналы, команды/логи, source manifests, patch и sources/worksheet. Не коммитить raw bags/кэши/секреты. Verdict CONFIRMED/REJECTED/INCONCLUSIVE; отдельно mechanism и merge readiness. Draft PR на русском. Никаких merge/auto-merge/main/чужих веток.

## Научная проверка до fitting

Farina & Piroddi, Simulation error minimization identification based on multi-stage prediction, IJACSP25:389-406, DOI10.1002/acs.1203 (online2010, volume2011). Consensus: прочитан abstract; Scite: metadata, закрытый доступ, дальнейший read_fulltext заблокирован месячной квотой. Контексты цитирующих работ/полный текст заново не доступны, independent verification не заявлять. Wiley403. Один источник мотивирует multi-step vs teacher forcing, не обещает выигрыш.

Wolfram Language проверил discrete actuator sum, sensitivity, small/long horizon, bias-vs-resistance ambiguity, mass/force scale gauge и dimensionless loss. Сохранить worksheet и фактический InputForm output, включая отдельную неудачную JSON-export попытку. Только actuator pole доказан stable; нелинейный clipped observer этим глобально не сертифицирован. SciPy1.17 docs подтверждают max_nfev отдельно от numerical-Jacobian calls.
