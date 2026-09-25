# H03: отрицательный исследовательский результат — не готов к merge

## Решение

**Гипотеза улучшения точности отвергнута для зафиксированного H03_w040.** Окно уменьшило шумовые train-прокси, но ухудшило fault-event group-macro RMSE на **2.256765%** при разрешённых 0.5%. Не достигнут ни минимум 2% clean gain, ни минимум 5% fault gain. Default остаётся adaptive_v5. Два других окна не прогонялись на validation: этот результат не доказывает невозможность всех вариантов H03.

## Алгоритм и границы изменения

[algorithm.patch](../../research/H03/algorithm.patch) заменяет двухточечное ускорение для disturbance медианой попарных наклонов по уже доступным FUSED, согласованным, model-consistent колёсным парам. Выбрано окно 0.40 с, максимум 7 сохранённых пар / 21 slope. Старт с двух точек без ожидания полного окна. История очищается при недоверенных входах, stale-команде, разрыве времени и reset; дубликаты не добавляются. Физические пределы ускорения/поправки и adaptation_tau_s=0.5 сохранены.

Runtime: только controller/front/rear, без GNSS/IMU, будущих samples и новых зависимостей. Измерение скорости, R, gate, reacquire, stop logic, физика и Timeline не меняются. Ошибки двух колёс не объявляются независимыми. `adaptation_window_s=0` сохраняет численное поведение baseline.

В PR патч оставлен **явно применяемым**, как отрицательные эксперименты v6: активный core/default не заменён. Реально применённый и измеренный core находится в executable freeze/result checkpoint ниже. Это не только предложение и не только unit-тест: выполнен replay реальных записей. [candidate.yaml](../../research/H03/candidate.yaml) — отклонённый исследовательский профиль, не для deployment.

Перед реализацией изучены v5/v6: дальнейшее сокращение tau до 0.25 с не прошло v5; projection/decay в v6 давали fault-регрессии. Эти механизмы H03 не меняет.

## Commit chain и фактический запуск

| Назначение | SHA |
|---|---|
| Общий baseline, adaptive_v5 | `984fdf2fc4faf05325249215d6b8541c0e68209a` |
| План до экспериментов | `5ac5e410b0a2cc4e4c62e243873f5f4cb16ba2ae` |
| Патч алгоритма | `35256ff582c7402ab9378440edb761c0c0b79953` |
| Исходники запущенного раунда | `b803b41e3ea6fb709eeb6dd63f0856f9111ab6bd` |
| Применённый core + train + freeze ДО validation | `b98ee50e890012f54e42b94edc79cf532f989952` |
| Все результаты и применённый core | `58402e4073c43af7c36e67a9f9bf2969be19ea38` |

[Actions run 36174944020, attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36174944020), job 108203175699: success. Это успешное выполнение исследования с отрицательным accuracy-решением, **не** прохождение acceptance gate.

По логу 25 сентября 2026: freeze закоммичен в 18:44:46 UTC, push завершён до запуска validation в 18:44:47 UTC. Runner перед validation проверил freeze в Git-коммите, исходники, модель и train-results hash. После validation параметры, evaluator и пороги не менялись.

## Train: ограниченный поиск

Ровно три зарегистрированных окна: 0.20 / 0.30 / 0.40 с. Обработаны 64 train-bag / 27 групп; 60 bag дали ненулевую общую диагностическую маску. Неизменный Store разрешает train только три vehicle-топика, без GNSS.

Offline target ускорения — прежняя wheel-derived Savitzky–Golay конвенция: 11 точек, degree=2, dt=0.1 с. Центрированное окно использует будущие точки только для offline target, никогда в observer. Это не независимая ground truth. Wheel-only mask: 467510 точек, общая конечная маска четырёх replay: 451778, непрерывных троек для roughness: 424292. Индивидуальные покрытия и пустые bag сохранены в исходных результатах.

| Профиль | Acceleration proxy RMSE, м/с² | Disturbance roughness¹ | Изменение roughness | Диагностический lag² |
|---|---:|---:|---:|---:|
| adaptive_v5 | 0.190693255 | 0.057770375 | 0% | 0.0 с |
| H03_w020 | 0.161236960 | 0.046691241 | −19.178% | 0.0 с |
| H03_w030 | 0.106262943 | 0.025915352 | −55.141% | 0.0 с |
| H03_w040 | 0.094395006 | 0.017642412 | **−69.461%** | 0.0 с |

¹ Group-macro RMS второй разности disturbance на общей непрерывной маске. Это прокси резкости, не независимое измерение шума.
² Минимальный proxy-RMSE на сетке 0/0.1/0.2 с. Нулевой выбранный lag не доказывает отсутствия запаздывания на переходах и не является ROS latency.

Все три прошли preregistered proxy-gates. Выбран H03_w040 по минимальной roughness; acceleration proxy RMSE уменьшился на 50.499%. Два других варианта сохранены как train-результаты, не использованы для повторного выбора по validation.

## Единственный validation: один измеритель

Служебные aliases evaluator: `baseline_v2` = adaptive_v5, `balanced_physics` = H03_w040. Это не старый v2 и не другой baseline.

13 файлов проверены побайтно против baseline: evaluate.py, experiment.py, manifest.py, export_bags.py, v6 compare.py, split, plan, Timeline, node, route и конфигурации. `ev.score/replay`, `ex.match/metrics`, distance и `v6.summary` неизменны. Общие timestamps/reference-маски; 20 Гц, delay=0. Fault anchor, warmup, bias/dropout/lock и recovery window точно повторяют v6.

Обработаны 19 bag / 10 групп; reference доступен в 9 группах / 30 bag-receiver парах. 76 fault-сценариев, 120 сравнений с reference, оба приёмника сохранены. Без reference: `30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30`; они не считаются нулевой ошибкой.

Baseline воспроизвёл опубликованный v5: **234 числовых поля, max absolute delta 0.0**. Это sanity check, не новый независимый test.

| Метрика | adaptive_v5 | H03_w040 | Изменение candidate/baseline − 1 |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.117138274 | 0.117348558 | +0.179518% |
| Fault-event group-macro RMSE, м/с | 0.538434411 | 0.550585612 | **+2.256765%** |
| Pooled clean RMSE, м/с | 0.216723603 | 0.216772741 | +0.022673% |
| Scalar span distance group-macro RMSE, м | 4.630977808 | 4.624096284 | −0.148598% |
| Сопоставленные clean-точки | 698891 | 698891 | без потери |
| False stops, clean / fault | 18 / 0 | 18 / 0 | без роста |
| Fault-сравнения без recovery | 0 | 0 | без роста |
| Причинность / unexpected resets, clean и fault | 0 / 0 | 0 / 0 | без нарушений |

Нет потери n/coverage и новых false stops ни в одном сравнении. Нарушений clean per-bag порога baseline + max(0.005 м/с, 5%) нет. Но fault aggregate хуже допустимых 0.5%, минимального выигрыша нет. **Отказ: `aggregate_regression:fault_rmse`, `insufficient_gain`.** Clean/fault/pooled aggregate tolerance 0.5%, distance 1%, gain 2%/5% не смягчались.

## Регрессии за агрегатами

Clean RMSE вырос в 24 из 30 сравнений; fault-event RMSE — в 58 из 120. Все RMSE-регрессии, даже небольшие, сохранены в исходном decision.json. Крупнейшие:

| Bag / receiver | Fault | Baseline RMSE, м/с | H03 RMSE, м/с |
|---|---|---:|---:|
| 30639_50956d6e / rover | dropout 10 с | 0.086759 | 0.765853 |
| 30639_50956d6e / master | dropout 10 с | 0.087057 | 0.765039 |
| 30639_50956d6e / rover | dropout 5 с | 0.075013 | 0.407572 |
| 30639_50956d6e / master | dropout 5 с | 0.077536 | 0.408772 |
| 30639_50956d6e / rover | lock 3 с | 0.080561 | 0.282495 |
| 30639_50956d6e / master | lock 3 с | 0.083811 | 0.283691 |
| 30618_49fe4c54 / master | dropout 10 с | 0.439924 | 0.568306 |
| 30618_2dbce472 / rover | dropout 10 с | 0.552379 | 0.669087 |
| 30618_68d1748a / master | dropout 10 с | 0.228632 | 0.334386 |
| 30618_68d1748a / rover | dropout 10 с | 0.227550 | 0.332411 |

Для 30639_50956d6e/rover dropout 10 с это +0.679094 м/с, **+782.736%**. Master подтверждает сильную регрессию, она не ограничена одним приёмником.

Максимальная clean-регрессия: 30618_437e855c/master, 0.042843732 → 0.043544908 м/с (+0.000701176, +1.637%), ниже фиксированного per-bag gate.

Recovery замедлилось в 14 сравнениях. Максимум: 30618_49fe4c54/master, bias 5 с, 0.205104267 → 1.005104267 с (**+0.8 с**), хотя невосстановлений нет. Локальная дистанционная регрессия: 30639_3b3d9eb8/rover, 26.522054181 → 26.725101172 м (+0.203046991 м); 30618_b15eafc3/rover, 0.317488852 → 0.320843352 м (+1.056573%). Все положительные изменения distance/recovery из уже сохранённых результатов перечислены в [posthoc_regressions.csv](posthoc_regressions.csv). Это перечисление, не новые измерения и не изменение gate. Distance-порог 1% относится к основной агрегированной метрике, не введён постфактум как per-bag gate.

## Фактические проверки и ограничения

В исследовательском job с применённым патчем: **48 unit tests PASS: 22 core/route + 10 timeline + 16 H03**. Первые два набора защищают отключённый default; H03-тесты включают окна, причинный prefix, reset/gap, rejection, stale/duplicate/future, startup, bound 7 и точное совпадение выключенного механизма с baseline на 2000 смешанных шагов. Локально дополнительно 16 H03 tests PASS.

Локальный дополнительный synthetic microbenchmark выполнен для baseline и всех трёх окон: 20000 вызовов step/вариант, affinity 2 CPU, RLIMIT_AS 500000000. Baseline p95 core-call 6.850 мкс; H03_w040 12.098 мкс. Это НЕ ROS, НЕ реальные записи, НЕ publisher→subscriber latency и НЕ доказательство ограничений установленного runtime. Четыре JSON и исходный локальный скрипт сохранены в supplementary delivery; ими параметры не выбирались.

**Установленный ROS H03, wall-paced частота, end-to-end latency и контейнерный benchmark 2 CPU / 500 MB для H03 не выполнялись.** Старые v5 проверки и synthetic timing не выдаются за них. После отрицательного accuracy-gate кандидат не продвигался на этот этап. Данные и запись GitHub доступны; неизвестные runtime-показатели не придуманы.

Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0. Train 185.993 с, validation 39.695 с — offline compute, не задержка ROS.

Validation уже многократно использовался; это не независимый final test. Train target выведен из колёс: хороший proxy не доказывает точность истинной скорости. Нулевой lag на сглаженной цели не исключает задержку переходов. Возможное объяснение fault-регрессий — неудачная disturbance-оценка перед потерей колёс, но отдельными трассами ускорения это здесь не доказано. Донастройка по этому validation в раунде запрещена.

Final-test bags не открывались SQL-загрузчиком и не использовались для разработки/оценки; штатный downloader распаковывает общий архив всех splits. В access только 64 train и 19 validation. Исторический final test не пересчитывался. Distance — scalar reanchored surrogate, не xyz/ENU/terminal drift. Common-mode ошибки колёс остаются неоднозначными; прежний масштаб 1/3.6 не переоценивался.

## Исходные результаты, неизменяемые ссылки

Все evidence в commit `58402e4073c43af7c36e67a9f9bf2969be19ea38`, directory `reports/research_H03/runs/H03-36174944020-1`:

- [Train results](https://github.com/jabrailkhalil/hack/blob/58402e4073c43af7c36e67a9f9bf2969be19ea38/reports/research_H03/runs/H03-36174944020-1/train/results.json), [train CSV](https://github.com/jabrailkhalil/hack/blob/58402e4073c43af7c36e67a9f9bf2969be19ea38/reports/research_H03/runs/H03-36174944020-1/train/per_bag.csv), [freeze](https://github.com/jabrailkhalil/hack/blob/b98ee50e890012f54e42b94edc79cf532f989952/reports/research_H03/runs/H03-36174944020-1/train/freeze.json).
- [Validation results](https://github.com/jabrailkhalil/hack/blob/58402e4073c43af7c36e67a9f9bf2969be19ea38/reports/research_H03/runs/H03-36174944020-1/validation/results.json), [все per-bag метрики CSV](https://github.com/jabrailkhalil/hack/blob/58402e4073c43af7c36e67a9f9bf2969be19ea38/reports/research_H03/runs/H03-36174944020-1/validation/per_bag.csv), [decision и все RMSE-регрессии](https://github.com/jabrailkhalil/hack/blob/58402e4073c43af7c36e67a9f9bf2969be19ea38/reports/research_H03/runs/H03-36174944020-1/validation/decision.json).
- В том же directory: `integrity.json`, `train/access.json`, `validation/access.json`, `validation/started.json`, `core-tests.log`, `timeline-tests.log`, `h03-tests.log`, логи зависимостей/датасета/этапов.

[Actions artifact](https://github.com/jabrailkhalil/hack/actions/runs/36174944020/artifacts/10882730688): 101 файл, ZIP SHA256 `92a4d9e3a311995d79e010a380b716a945e89ad039f5e0e80e6c56ca9fd246e1`. Помимо artifact evidence сохранён в checkpoint-ветках с run_id/run_attempt/H03.

## Выполненные команды

Source b803b41, Python 3.13.5, OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1; H03_OUTPUT=reports/research_H03/runs/H03-36174944020-1:

```bash
python -m pip install -r requirements-research.txt
git apply --check research/H03/algorithm.patch
git apply research/H03/algorithm.patch
python research/H03/run.py integrity --output "$H03_OUTPUT/integrity.json"
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p test_core.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p test_timeline.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/H03 -p test_h03.py -v
python tools/get_dataset.py
python research/H03/run.py train --output "$H03_OUTPUT/train"
# Затем commit + push checkpoint/H03-freeze-36174944020-1, ДО validation.
# H03_FREEZE_SHA=b98ee50e890012f54e42b94edc79cf532f989952
python research/H03/run.py validate \
  --freeze "$H03_OUTPUT/train/freeze.json" \
  --output "$H03_OUTPUT/validation" --workers 2
```

## Повтор frozen candidate без нового подбора

В авторизованном клоне:

```bash
git fetch origin checkpoint/H03-result-36174944020-1
git worktree add --detach ../hack-H03-reproduce 58402e4073c43af7c36e67a9f9bf2969be19ea38
cd ../hack-H03-reproduce
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H03_FREEZE_SHA=b98ee50e890012f54e42b94edc79cf532f989952
python research/H03/run.py validate \
  --freeze reports/research_H03/runs/H03-36174944020-1/train/freeze.json \
  --output "/tmp/H03-validation-$(date +%s)-$$" --workers 2
```

В result checkpoint patch уже применён. Для полного повтора train→freeze→validation использовать зафиксированные source/workflow и новый output, сохраняя commit barrier. Оригинальный run не переписывать.

## Все clean per-bag/receiver RMSE

CSV выше также содержит MAE, bias, p95, coverage, n, distance, fault/recovery. Четыре bag без reference перечислены выше; их метрики N/A.

| Bag | Receiver | Baseline, м/с | H03_w040, м/с | Изменение |
|---|---|---:|---:|---:|
| 30618_0686195f | master | 0.094452304 | 0.094115114 | -0.357% |
| 30618_0686195f | rover | 0.094170108 | 0.093811070 | -0.381% |
| 30618_2dbce472 | master | 0.130075572 | 0.130217349 | +0.109% |
| 30618_2dbce472 | rover | 0.057647387 | 0.058026260 | +0.657% |
| 30618_2f104a1d | master | 0.031473771 | 0.031933673 | +1.461% |
| 30618_2f104a1d | rover | 0.067776972 | 0.067976909 | +0.295% |
| 30618_437e855c | master | 0.042843732 | 0.043544908 | +1.637% |
| 30618_437e855c | rover | 0.043447871 | 0.044064330 | +1.419% |
| 30618_49fe4c54 | master | 0.037652351 | 0.037794017 | +0.376% |
| 30618_49fe4c54 | rover | 0.899881383 | 0.899856076 | -0.003% |
| 30618_68847170 | master | 0.030245108 | 0.030672757 | +1.414% |
| 30618_68847170 | rover | 0.046760547 | 0.047011859 | +0.537% |
| 30618_68d1748a | master | 0.147618205 | 0.147292611 | -0.221% |
| 30618_68d1748a | rover | 0.321360612 | 0.321462332 | +0.032% |
| 30618_76e1f9c7 | master | 0.040516075 | 0.041059767 | +1.342% |
| 30618_76e1f9c7 | rover | 0.041029762 | 0.041551381 | +1.271% |
| 30618_b15eafc3 | master | 0.032322455 | 0.032685057 | +1.122% |
| 30618_b15eafc3 | rover | 0.033179249 | 0.033517167 | +1.018% |
| 30618_b8044aa0 | master | 0.032019489 | 0.032472680 | +1.415% |
| 30618_b8044aa0 | rover | 0.031806330 | 0.032276626 | +1.479% |
| 30618_defd0170 | master | 0.114357219 | 0.114170984 | -0.163% |
| 30618_defd0170 | rover | 0.114253227 | 0.114073255 | -0.158% |
| 30639_3b3d9eb8 | master | 0.215702210 | 0.215790769 | +0.041% |
| 30639_3b3d9eb8 | rover | 0.216673117 | 0.216759993 | +0.040% |
| 30639_50956d6e | master | 0.129200873 | 0.129213990 | +0.010% |
| 30639_50956d6e | rover | 0.371332086 | 0.371376310 | +0.012% |
| 30639_9f0b519f | master | 0.038139898 | 0.038745870 | +1.589% |
| 30639_9f0b519f | rover | 0.039010407 | 0.039538820 | +1.355% |
| 30639_d601d28f | master | 0.105715414 | 0.106386386 | +0.635% |
| 30639_d601d28f | rover | 0.112789675 | 0.113370124 | +0.515% |
