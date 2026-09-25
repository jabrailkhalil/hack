# H18 — PLAN до экспериментов

Round `R2-v7-fixed`. Baseline `65bba39ed05c781f3f69a65c02f69931152cbfd9`, `GuardedReadoutObserver`, `guarded_readout_v7.yaml/json`, readout gain=1 / holdoff=0.5, wheel_time_compensation=0, adaptation_tau=0.5, 20 Hz, delay=0. Ветка `research/round2-H18`. Сравнивать возвращённый Estimate/last_estimate, не внутренние v/s. Ни H11/v8, ни движущийся main не включаются.

До этого PLAN выполнены только чтение и доставка pinned исходников; measurement payloads не открывались, тесты/эксперименты H18 не запускались. Source-only workflow не выполняет эксперимент. Изучены core/readout/Timeline, canonical launch/profile, evaluator, роли и исторические v5/v6; PR #18/H10, #14, #23, #26; H07 уже исследован отдельно. Результаты иных агентов R2 не используются.

## Ровно один вариант, без расширения бюджета

`fixed_consider`: фиксированная train-calibrated Pdd. Второй causal residual-based вариант НЕ исследуется. Baseline и feature-off — контроли, не кандидаты. Random walk d не включается (Qd=0). Непрерывного поиска, подбора Qv-множителей, изменения guards/физики/readout нет.

Runtime будет отдельным subclass GuardedReadoutObserver в новом модуле; существующие core.py, guarded_readout.py, node, Timeline и профили сохраняются побайтно. Подключение только через отдельную research factory. Default checkout не включает H18.

## Механизм, допущения и lifecycle

Хранить только фиксированную Pdd и скаляр Pvd, timestamp последнего нового ACCEPTED wheel, флаг outage и ограниченное число диагностических скаляров. Legacy mean d/drive_a, их обновления, numerical integration, raw guards, hard innovation cap, bounded reacquisition остаются в базовом коде. Изменять только входную pv перед неизменным шагом; через неё меняется прежний scalar gain (и прежняя covariance-dependent часть soft gate, но НЕ hard cap). Это риск ложного принятия, обязательный safety gate ниже.

Outage начинается причинно после `max_age_s=0.25` без нового принятого wheel sample (по его source stamp). Для шага h использовать только пересечение [old_t,t] с превышением этого возраста. При обычных wheel updates дополнительный covariance transport выключен; никакого ожидания будущего измерения. Первое вернувшееся измерение получает накопленную variance; после него дополнительный transport прекращается, но pv и корреляции НЕ сбрасываются. Следующие scalar corrections продолжают сжимать Pvd через Schmidt/Joseph factor.

Локальная модель ошибок: ev'=ed+w_v, ed'=0. F(h)=[[1,h],[0,1]]. Дополнительный transport: pv += 2*h*Pvd + h*h*Pdd; Pvd += h*Pdd. Штатный core отдельно добавляет исходный Qv*h, включая прежний stale-command множитель. Нельзя добавлять Qv дважды.

У ошибки d и скорости общие wheel-источники; независимость не предполагается. При начале нового outage неизвестную корреляцию консервативно переякорить как Pvd=+sqrt(pv*Pdd). Для h>=0 это максимальная scalar prediction variance среди |Pvd|<=sqrt(pv*Pdd). Это PSD rank-one и верхняя граница именно скалярного forward variance при заданных маргиналах, НЕ утверждение Loewner-доминирования любой совместной covariance. При повторном outage положительная корреляция только повышается до границы; pv и Pdd не уменьшаются. До первого outage Pvd=0 и dormant; эта переменная не выдается за точную covariance фактического nonlinear estimator.

Коррекция только v, Kd=0: Pvv+=(1-K)^2*Pvv-+K^2*R; Pvd+=(1-K)*Pvd-; Pdd+=Pdd-. Среднее d НЕ корректируется этим innovation. Использовать K, восстановленный из scalar Joseph identity Ppost/Pprior (как существующий readout); variance floor сохраняется и отдельно проверяется. При bounded reacquisition не считать increment независимым measurement: Pvd не уменьшается, scalar variance floor только увеличивает Pvv. При STOPPED не заявлять нулевую Pdd; сохранить маргинальную pv и допустимую корреляцию. Явный reset возвращает базовое состояние и dormant lifecycle, Pdd остается фиксированным настроечным параметром. Legacy d может изменяться при возвращении trusted wheels; следующий outage переякоряет cross-correlation без создания искусственной уверенности.

Ограничение: это episode-wise consider approximation, а не точная covariance clipped observer. Не моделируются actuator-history uncertainty, nonlinear Jacobian и неизвестная cross-correlation legacy адаптации вне outage. Pdd из wheel pseudo-label не является независимой истиной. В белом Qv уже может присутствовать часть той же ошибки; double-counting обсуждается, но Qv не переобучается.

## Train calibration (только vehicle)

Все 64 bags настоящей train-роли; baseline canonical v7, без GNSS. На шагах, где штатная adaptation действительно разрешена: два новых agreeing/gated wheels, свежая команда, 0.05<=pair_dt<=max_age_s, |measured_a|<=max_accel, |wheel_mean|>0.5. Residual: measured_a - drive_a + resistance(inner_v_after_correction) - d_before_step. Только текущие/прошлые wheel samples.

Для подавления шума derivative агрегировать последовательные trusted residuals в неперекрывающиеся блоки длиной не менее 0.5 s (не менее трех residuals, разрыв не больше 0.25 s). Target блока — средний residual, ограниченный [-2*disturbance_limit,2*disturbance_limit]. Для каждой исходной группы вычислить средний квадрат по всем её блокам; Pdd_raw — среднее этих group means. Pdd=clip(Pdd_raw,1e-6,disturbance_limit^2) в m^2/s^4. Это second-moment scale, не unbiased variance estimate и не wheel disagreement.

Достаточность train: >=100 блоков и >=5 исходных групп, иначе INCONCLUSIVE без development/validation. Сохранить статистику и все group/bag contributions, limits, число clipped blocks и access journal. Никаких альтернатив параметра после получения метрик.

## Математика и источники

Wolfram: FPF^T + integrated Q; Pvv(T)=Pvv0+2*T*Pvd0+T^2*Pdd0+Qv*T; для справки Qd*T^3/3, Qd*T^2/2, Qd*T. Проверить Schmidt/Joseph, determinant PSD, предел h=0, размерности и upper bound при неизвестной корреляции. Random-walk terms вывести, но не включать. Сохранить worksheet и фактический вывод. NumPy property tests и finite difference локальной v'=d модели не доказывают accuracy.

Consensus: узкий поиск Schmidt/consider; выбран источник Zanetti/Bishop (2012), Kalman Filters with Uncompensated Biases, JGCD 35:327-335 — доступная карточка/вводный текст, не полный текст. Scite фактически отказал из-за monthly MCP limit; citation contexts/fulltext не проверены. Не покупать доступ. Источники мотивируют механизм, но не подтверждают наш результат.

## Данные, baseline, driver

Новый isolated driver, factory канонического v7 и H18. Использовать неизменные evaluate.score/replay, matching, метрики, fault placement из research_guarded.fault_windows и group aggregation из research_v6. Legacy aliases baseline_v2/balanced_physics используются только для совместимости score: оба контрольных alias означают canonical v7, явно переименовать после score. Независимо сравнить driver baseline с прямым canonical factory и feature-off, включая все outputs/счётчики. Проверять новый SHA256 manifest, не переписывать старые pins.

Development loader проверяет настоящую development membership до SQLite, checksum и read-only URI; принимает только controller/front/rear и два внешних reference. Train GNSS закрыт. Validation через штатный Store. Test/final measurements не открывать. Все 17 development bags / все предусмотренные группы; не выбирать bags по ошибке.

До quantitative candidate comparison: unit/compile, feature-off exact equality, prefix causality, stale/future/duplicate/reset, zero-lock/genuine stop, bounded reacquisition, no NaN, constant history size, PSD/Joseph/local finite differences. На development driver baseline и независимый canonical replay должны совпасть; при расхождении исправлять инфраструктуру ДО сравнения.

## Заранее фиксированные suites / coverage / safety

Original suite без изменения: bias front +5 на5s, dropout both 5/10s, lock both3s, те же vehicle-only anchors и окна. Отдельная diagnostic suite на тех же anchors: common +5 both 0.7/1.2s; dropout5s с последующим common +2 both на1s; отдельно genuine dropout5s recovery. Диагностика не заменяет admission original suite.

До validation должны быть >=10 original/diagnostic outages на >=3 development groups, >=200 active covariance ticks и >=10 реально изменённых принятых wheel updates (gain или v delta >1e-9). Иначе INCONCLUSIVE (механизм не покрыт), не отрицание семейства. В safety suite сравнивать число ACCEPTED и REACQUIRE_ACCEPTED wheel statuses внутри known corrupted intervals только во внешнем scorer. Любой рост false acceptance относительно baseline в конкретном сценарии, дополнительные false stops/новые unrecovered/causality/reset — REJECTED и validation не открывать.

Development regression guard: те же лимиты aggregate/per-bag/coverage, что ниже; минимальный gain на development не обязателен для единственного кандидата. При нарушении любого regression/safety gate кандидат REJECTED, без validation. При достаточном coverage и safety — отдельный freeze commit с code/config/data/split/driver/evaluator hashes, train и development decisions ДО любого validation IO.

Затем один paired validation. Не менять параметры после него. Допустим только повтор того же freeze при infrastructure failure/verification с новым run ID, без выбора удачного прогона. При недоступном исполнении/данных INCONCLUSIVE; частичные результаты не выдаются за full validation.

## Общий R2 численный контракт (не менять)

Clean group-macro RMSE gain>=2% ИЛИ original fault-event gain>=5%. Каждая clean/fault/pooled ошибка <=baseline*1.005. Scalar-span distance aggregate <=baseline*1.01. Clean каждый bag/receiver <=baseline+max(0.005m/s,0.05*baseline). Coverage и n одинаковы, false stops не растут в каждой паре, новые individual unrecovered запрещены, causal errors/resets=0. Baseline=0: допускается только delta<=1e-12 для aggregate численной погрешности; нулевой baseline не даёт relative gain. Missing reference остается missing, не ноль. Показать также MAE/bias/recovery и локальные регрессии.

## Стоимость, ROS, evidence

Первый development bag по замороженному списку, все его events. Одинаковый сбор outputs; один прогрев каждого; затем AB,BA,AB,BA, threads OMP/OPENBLAS=1. Раздельно wall/process CPU для replay и прямого step с заранее записанным причинным расписанием inputs, baseline и candidate. RSS измерять отдельно/честно обозначать что измерено; offline != ROS latency. При прохождении accuracy обязательны fresh installed ENABLED candidate ROS offline 2CPU/500000000 bytes, оба clock modes, real development replay. При уже отклонённой точности полный ROS benchmark разрешено пропустить с явной отметкой.

reports/research_R2/H18/<run-id>/: PLAN/freeze, русский REPORT, patch/config/source hashes, команды/логи, raw и per-bag/receiver/fault, diagnostics/trace excerpts, источники и worksheet. Не коммитить raw bags/caches/secrets. Source commit, freeze и поздний report commit различать. Draft PR на русском с verdict и фактическими ограничениями; REJECTED/INCONCLUSIVE — исследовательский артефакт, не готов к merge. Ни merge, ни auto-merge.

## Команды предусмотренного driver

```bash
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2/H18 -p 'test_*.py' -v
python tools/get_dataset.py
python research/R2/H18/run.py train --output "$OUT/train"
python research/R2/H18/run.py development --training "$OUT/train/calibration.json" --output "$OUT/development"
# только после safety/coverage/regression PASS: separate freeze commit+push
python research/R2/H18/run.py validation --freeze "$OUT/FREEZE.json" --output "$OUT/validation"
```
