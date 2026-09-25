# H18 — R2-v7-fixed: предварительный план

Baseline: 65bba39ed05c781f3f69a65c02f69931152cbfd9, GuardedReadoutObserver, guarded_readout_v7.yaml/json, readout gain=1, holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau_s=0.5, output 20 Hz, alignment_delay=0. Сравниваются возвращаемые Estimate, не внутренние v/s. H11/v8 не включается.

Ветка research/round2-H18 уже существовала на 2ddf918ec990085f070caed003e24b616ce27fe8; её содержимое/результаты не используются. Эта независимая попытка: research/round2-H18-covariance-20260925, создана от общего baseline. Не менять main, чужие ветки, старые pins/отчёты; не merge/auto-merge.

## Единственный вариант (budget=1, baseline/off не считаются)

Fixed train-calibrated consider covariance для эпизодов отсутствия принятых wheel updates. Среднее предсказание, drive_a, legacy d/adaptation, численное интегрирование, readout, raw rate/range/timestamp/disagreement/zero-lock guards и bounded reacquisition остаются исходными. Runtime — новый subclass GuardedReadoutObserver, без патча старых модулей.

Когда после инициализации прошло больше Config.max_age_s с последнего ACCEPTED wheel update, начинается covariance-эпизод. Он не зависит от injected-fault флага, reference, bag ID или будущих samples. Вне эпизодов до первого outage — точный baseline. Один вариант, никаких Qv множителей и Qd random walk: данные не обосновывают Qd и это был бы другой вариант.

Новый nuisance error — неопределённость удерживаемого d. На старте эпизода неизвестную cross-correlation ограничиваем PSD envelope diag(2*Pvv,2*Vd): для любой |Pvd|<=sqrt(Pvv*Vd) разность с [[Pvv,Pvd],[Pvd,Vd]] PSD. Это консервативная декорреляция, не произвольное удвоение Q. Далее F=[[1,dt],[0,1]], Pvv+=2*dt*Pvd+dt^2*Pdd плюс прежний Qv*dt (и прежний stale multiplier), Pvd+=dt*Pdd, Pdd постоянно. При velocity correction используем прежний scalar gain; Schmidt/Joseph Kd=0 даёт Pvd*=(1-K), Pdd не уменьшается. После первого реально выполненного legacy d adaptation или STOPPED nuisance-эпизод маргинализируется: накопленное Pvv не уменьшается, cross/Pdd больше не распространяются до нового outage. Это не утверждение точной covariance для нелинейного clipped observer: derivative pseudo-label, actuator-history uncertainty и корреляции с адаптацией не моделируются полностью. Перезапуск nuisance после нового доверенного mean reanchor — объявленное допущение. Explicit reset возвращает исходные prior и все счётчики.

Добавочный Pvv вводится перед исходным GuardedReadoutObserver.step, поэтому неизменный readout восстанавливает gain из фактического prior, а не устаревшего линейного prior. Hard innovation cap неизменен; рост мягкого gate возможен и проверяется отдельно на false acceptance.

## Train calibration, без GNSS

Пройти все 64 штатных train-bag только исходным baseline. Использовать только причинные пары свежих ACCEPTED согласованных колёс, валидную команду, 0.05<=delta wheel stamp<=max_age_s, |wheel acceleration|<=max_accel, |wheel mean speed|>0.5. Residual=wheel acceleration-drive_a+resistance(v_after_correction)-d_before_update (именно ошибка baseline adaptation target). Квадрат residual ограничить сверху (2*disturbance_limit)^2. Для каждой группы вычислить mean squared residual; Vd=90-й percentile этих group means, ограниченный [0.0025,0.36] (m/s^2)^2. Не считать колёсное расхождение независимой полной ошибкой d. Сохранить clipped count, все per-bag/group stats. Минимум 1000 eligible residuals и 5 групп; иначе INCONCLUSIVE без validation. Единственный детерминированный calibrator, без оптимизации по GNSS или расширения диапазонов.

## Development и stop rule

Использовать настоящие 17 development-bag через новый read-only role loader. Train/validation loader и split не менять. Runtime имеет только vehicle inputs; оба reference receiver доступны только внешнему evaluator. Оценить baseline, candidate off и единственный calibrated candidate на всех development clean и исходных faults. Сетка, score/matching/distance/fault anchors/group aggregation импортируются из pinned evaluator. Добавить отдельный общий R2 gate, не редактировать исторические decide/pins.

Перед validation обязательны: disabled exact Estimate/status/counter equivalence; causal prefix, duplicate/stale/future/reset/finite/O(1) tests; Joseph matrix/PSD/closed-form/finite-difference tests; реальные активации >=10 эпизодов в >=3 development-группах и >=100 active ticks; common-mode safety и genuine recovery отдельно. На тех же vehicle-only anchors отдельная diagnostic suite: common +5 m/s на обеих тележках на 0.7/1.2 s, ramp +1 m/s за 1 s с удержанием до 2 s, и dropout 5 s с ложной согласованной парой +2 m/s в последующие 1 s. Это диагностические наборы, не замена original admission.

False acceptance: число corrupted wheel updates со статусами ACCEPTED/REACQUIRE_ACCEPTED в диагностическом fault interval. Любой рост относительно baseline, новые false stops/unrecovered, causality/reset/nonfinite failures => REJECTED без validation. Недостаточная активация => INCONCLUSIVE. Если safety/coverage пройдены, единственный вариант допускается к одному validation даже если development gain ниже admission: параметры не меняются, negative validation разрешён. Это правило задано заранее.

## Freeze и validation

После train/development опубликовать отдельный freeze commit до validation с source/candidate/config/data/split/driver/evaluator hashes. Один paired validation на всех 19 штатных validation-bag, 76 original fault scenarios; оба receiver; одинаковые timestamps/masks. Сначала воспроизвести baseline тем же driver и независимой прямой canonical factory на development; подтвердить config/launch. Исторические v7 цифры — лишь cross-check после исполнения, не замена прогона. Не читать test payloads и не перенастраивать после validation. Infrastructure retry того же freeze — отдельный run, без выбора удачного результата.

Admission: >=2% clean group-macro RMSE gain ИЛИ >=5% original fault-event group-macro RMSE gain. Clean/fault/pooled regression <=0.5%, scalar-span distance <=1%, clean per-bag/receiver <=baseline+max(0.005,0.05*baseline). Без потерь n/coverage, дополнительных false stops, новых индивидуальных unrecovered, causal errors или unexpected resets. При baseline=0: абсолютный допуск 1e-12 для численных метрик, ноль для counters; gain по нулевой метрике не засчитывается. Отдельно MAE, signed bias, recovery distributions, локальные регрессии и missing reference. Группы, не receiver/ticks, являются независимыми единицами.

## Диагностика и стоимость

Сохранить первые/последующие gains при genuine recovery, Pvv/Pvd/Pdd до/в/после outage, error^2/Pvv descriptively, факт активации/изменения траектории, corrupted acceptance, bounded-memory counters. Не заявлять calibrated CI. На первом лексикографическом development-bag после 10 s warmup три AB/BA пары повторов с OMP/OPENBLAS=1; одинаковые outputs, replay process CPU и wall отдельно, step CPU отдельно на одинаковой captured input sequence. RSS процесса отдельно; не считать offline timings installed ROS latency. При accuracy reject полный ROS benchmark не требуется и отмечается not executed. При accuracy pass необходим свежий enabled installed ROS offline 2 CPU/500000000 bytes в обоих clock modes с real development replay, иначе INCONCLUSIVE/not ready.

## Команды и публикация

python tools/get_dataset.py
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2/H18 -p 'test_*.py' -v
python research/R2/H18/run.py --stage train --output <fresh>/train
python research/R2/H18/run.py --stage development --training <fresh>/train --output <fresh>/development
# отдельный commit/push FREEZE.json до любой validation IO
python research/R2/H18/run.py --stage validation --freeze <committed>/FREEZE.json --output <fresh>/validation

Все стадии сохраняют access journal до SQLite IO и отказывают для test. Evidence: reports/research_R2/H18/<run-id>/, уникальная checkpoint ветка, без raw bags/secrets/caches. Русский Draft PR с REJECTED/INCONCLUSIVE/CONFIRMED, отдельно mechanism и merge-ready. Checkout не меняет default: candidate включается явной H18 factory с calibrated Vd.

## Изученные предшественники и научный контекст

Прочитаны runtime core/guarded_readout/Timeline/config, старые evaluator/compare и v3/v5/v6. PR #18 H10 менял совместное mean [v,d] и Qd=0.04, был отклонён; H18 этого не повторяет. v5 process-noise x4 ухудшал faults/false stops; не использовать произвольный Q multiplier. H07 #22 и v6 projection/decay — отрицательные примеры по прежнему baseline. PR #14/#23 дают canonical output-only guarded v7. PR #26/H11 — quarantine common RATE_ANOMALY, изучен отдельно, не включён.

Consensus найден и fetched: Zanetti/Bishop, Kalman Filters with Uncompensated Biases (2012), DOI 10.2514/1.55120; реально прочитана карточка/abstract-like introduction, не весь текст. Primary author bibliography подтверждает DOI (pages 327-330; Consensus metadata 327-335 различается). Scite actual attempt: monthly MCP usage limit, full text/citation context НЕ прочитаны. Wolfram выполнил symbolic FPF'+Q, Qd terms, Schmidt Joseph, PSD-envelope determinant p*d-c^2, zero-time and semigroup. Исполнимый worksheet и фактический текст вывода сохранить. Аналитика не доказывает real-bag accuracy.
