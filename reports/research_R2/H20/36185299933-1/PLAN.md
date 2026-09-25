# H20 / R2-v7-fixed — предварительный план

Статус: предрегистрация ДО реализации/численных replay-экспериментов. Этот файл не переписывать.

## База и границы

Baseline `65bba39ed05c781f3f69a65c02f69931152cbfd9`: реальный `GuardedReadoutObserver`, `guarded_readout_v7.yaml`, readout gain=1, holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau_s=0.5. Сравниваются возвращаемые Estimate/last_estimate, не внутренние v/s. 20 Hz, delay=0. Только controller/front/rear. Main/H11/v8 не включаются. Ветка `research/round2-H20` создана от этого SHA; main/чужие ветки/старые отчёты не изменяются. PR только draft, без merge/auto-merge.

Прочитаны core/guarded readout, v6 и PR #14/#23/#26, отрицательные H02 #15 и H05 #17. H20 не меняет age-R, TTL-history, recovery или readout. H01/v6 показывают, что небольшая поправка inner state может влиять на последующий model-only участок: такое влияние не считать доказанной причиной без трассы.

## Механизм и единственные варианты

Две заранее заданные силы: alpha=0.25 и alpha=0.50. Alpha=0 — обязательная ablation, не вариант подбора. Бюджет не расширять. Остальные параметры не подбирать.

Для уже принятых прежними hard gates колёс: e_i=sign(v_pred)*(z_i-v_pred). m=+1 для тяги, -1 для торможения, 0 для неопределённого режима. b=3*wheel_sigma_mps. x_i=max(0,m*e_i); q_i=x_i^2/(b^2+x_i^2); w_i=1/(1+alpha*q_i). В разрешённом режиме z_w=sum(w_i*z_i)/sum(w_i). R_w=max(R_original,R_base*max(1,abs(z_w-v_pred)/b))/mean(w_i); R_base — исходный correlation floor (sigma^2 для согласованной пары, 4*sigma^2 для одного/несогласованного принятого канала). Никакого деления R на число колёс. R_original включает прежний symmetric innovation penalty. Weight ограничен [1/(1+alpha),1]; общий вес не повышается.

Для alpha=0, m=0 либо всех w_i=1 возвращать исходные z,R без нового округления. Не менять исходные samples/stamps, абсолютную wheel scale, hard gates, disturbance formula/tau, stop/recovery, Timeline, matching, readout или физические параметры. Только две точки расширения в изолированной копии core: получение уже рассчитанного модельного контекста и soft weighting после всех прежних gates. Канонические файлы не перезаписывать; research factory загружает отдельную patched-копию вместе с неизменным guarded readout.

Режим: |v_pred|>=0.5 м/с, согласованный знак предыдущей скорости и прогноза; свежая валидная команда. Тяга: u>deadband+0.05 и sign(v_pred)*drive_target, sign(v_pred)*drive_a, sign(v_pred)*a_model >0.05 м/с². Торможение: u<-(deadband+0.05), все три направленных ускорения <-0.05 м/с². Иначе симметричный fallback. Режим/направление должны быть непрерывно согласованы >=0.5 s; смена режима, stale command, near-zero или рассогласование немедленно сбрасывают подтверждение. Хранить только фиксированное число скаляров и последнее диагностическое значение; никаких растущих историй.

## Предположения и риски

Знак controller не равен истинному ускорению. Общая ошибка колёс не становится наблюдаемой. Односторонний штраф даёт bias даже на симметричном шуме; это риск замедления настоящего разгона/торможения, а не бесплатная робастность. Применимость автомобильной slip-мотивации к двум тележкам не считается доказанной.

Источники: Bai et al., Sensors 24(13), 4137 (2024), DOI 10.3390/s24134137, физическая мотивация раздела 4.3/формулы 32; Tanelli/Savaresi/Cantoni (2006), Longitudinal vehicle speed estimation for traction and braking control systems, abstract через Consensus (четыре колеса + acceleration sensor, не наш интерфейс). Scite вызван, но вернул monthly MCP limit; карточки/контексты не прочитаны. Wolfram worksheet проверяет предел alpha->0, непрерывность, weight/correction bounds, Joseph identity, локальный symmetric-noise bias и rank/nullspace общей wheel ошибки; сохраняются фактические ответы, включая предупреждения численного интегрирования. Аналитика не доказывает accuracy на bags.

## Данные, sanity и coverage ДО validation

Не открывать test/final measurement payloads. Использовать штатный read-only Store для train vehicle-only и отдельную разрешённую development роль из исходного split; не переименовывать validation. Все 17 development bags, не выбирать удачные записи. Train не нужен для идентификации: физика и параметры фиксированы; при smoke использовать только vehicle inputs без train GNSS. Сначала независимо выполнить pristine v7 и disabled candidate одним неизменным replay; сравнить все возвращаемые поля и baseline state на каждом такте, runtime counters и timestamps.

Sanity: compileall; core/Timeline/guarded tests; alpha bounds; reverse direction; stale/future/nonfinite timestamps; duplicate reuse; explicit reset; causal prefix; bounded state; finite outputs; low-speed common zero lock; unchanged bootstrap/recovery when off. Не ослаблять исторические source-hash guards; отдельно сообщить их статус.

Coverage: на clean development не менее 200 реально изменённых accepted updates суммарно и не менее 5 s подтверждённой тяги И 5 s подтверждённого торможения в каждом из хотя бы двух исходных development groups. Дополнительная диагностика должна активировать оба направленных знака. При нехватке coverage — INCONCLUSIVE без validation, не опровержение семейства.

## Заранее объявленная диагностика

На каждом development bag earliest eligible vehicle-only anchor отдельно для тяги/торможения (grid |mean wheel|>1, |u|>deadband+0.05, >=25 s от начала и >=25 s до конца, знак mean wheel finite). Фаза anchor фиксируется по vehicle grid, не GNSS/ошибке модели. Пропуск anchor записывается как отсутствие coverage, не нулевая ошибка.

Для каждого найденного режима: front и rear отдельно; оба знака bias +/-0.3 м/с на 4 s; gradual slip +/-0.8 м/с (2 s линейный рост +2 s спад); common-mode gradual +/-0.8 м/с на оба колеса; общий lock 3 s. Кроме того synthetic clean traction/coast/braking в обоих направлениях, mismatch истинного ускорения и команды, общий smooth fault и dropout. Дополнительные suites отдельно от original admission suite, не подменяют её.

Сохранять sign innovations/weights, activation fractions, mode seconds и ограниченные трассы до/во время/после fault. Публиковать MAE, signed bias, recovery и локальные регрессии. Диагностика противоположного знака не отбрасывается. Safety: no added false stops/unrecovered/causal errors/unexpected resets/coverage loss. Clean phase/model-mismatch диагностические RMSE-регрессии >max(0.005 м/с,5% baseline) отмечаются как safety failure и блокируют validation. Диагностический выигрыш не заменяет original-suite gain.

## Выбор и неизменный контракт

На development сравнить оба варианта. Допустимый для validation: sanity/coverage/diagnostic safety выполнены; clean/fault/pooled aggregate regression<=0.5%, scalar-span distance<=1%, clean per-bag/per-receiver<=baseline+max(0.005 м/с,5%), без дополнительных false stops/невосстановлений/coverage loss/causal errors/resets. Требование gain на development не обязательно; из допустимых выбрать минимальный original fault group-macro RMSE, затем clean RMSE, затем меньший alpha. Если есть покрытие, но оба нарушили safety/regression — REJECTED проверенных вариантов без validation.

Перед любым validation опубликовать ОТДЕЛЬНЫЙ freeze commit: выбранный alpha, measured source SHA, SHA256 code/patch/config/split/data/driver/evaluator и development results. Затем ровно один paired validation. Никаких изменений по его результатам. Повтор только того же freeze для инфраструктуры/воспроизводимости с отдельным run ID.

Validation admission: clean group-macro RMSE gain>=2% ИЛИ original fault-event group-macro gain>=5%; одновременно clean/fault/pooled regression<=0.5%, scalar-span distance<=1%, per-bag clean<=baseline+max(0.005 м/с,5%), no coverage loss/additional false stops/new unrecovered/causality violations/unexpected resets. Для baseline=0: абсолютная дельта, допускается не более 1e-12 численного шума; gain относительно нуля не заявлять. Использовать неизменные score/replay/matching/fault_windows/summary/decide; недостающие pooled/unrecovered per-case guards добавить отдельно без ослабления legacy. Два receivers одной поездки не независимые группы. Не бутстрепить ticks.

## Стоимость, команды, evidence

После warmup на первом development bag в порядке split: шесть AB/BA пар на одинаковом потоке, threads=1, одинаковый сбор output, отдельно CPU/wall. RSS и installed ROS latency не приписывать Python replay. Если accuracy отклонена, installed ROS benchmark пропустить с явной отметкой. Если accuracy проходит, нужны enabled installed candidate, оба clock modes, реальный development replay under 2 CPU/500000000 bytes до CONFIRMED/merge readiness.

Планируемые команды (фактический журнал сохранять отдельно):
```bash
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/R2/H20/tests -v
python research/R2/H20/run.py --stage development --output "$OUT"
# Только при eligibility: отдельный опубликованный freeze commit.
python research/R2/H20/run.py --stage validation --output "$OUT"
```

Новый isolated factory/driver, старые pins не переписывать. Checkpoint `checkpoint/R2-H20-<run_id>-<attempt>`, отдельные directories `reports/research_R2/H20/<run_id>-<attempt>/`. Raw bags/секреты/кэши не коммитить. Отчёт на русском, raw JSON/CSV/per-bag/per-receiver/per-fault, access journal, patch, точные SHAs, команды/логи, sources/worksheet. Merge readiness отдельно от механизма. Невыполненная стадия обозначается точно; не придумывать CI/метрики/PR. При блокировке исполнения INCONCLUSIVE; исследовательский артефакт, не готов к merge.
