# R4-H36 — завершение после загрузки dataset(3).zip

**REJECTED. Исследовательский отрицательный результат, не готов к merge.** Новый архив подтвердил прежние данные и результат. Коэффициенты не подбирались повторно; validation и final test не открывались.

## Подтверждённое происхождение

Baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`, полный tree `eae49a504bc59b5c9b408445150bef32e111956f`. Весь пользовательский source ZIP вновь проверен: 301 исходный файл, bytes/paths/modes совпали. Его SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`.

Присланный `dataset(3).zip`: 256294592 байта, SHA256 **d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52**. Проверены все 64 train и 17 development DB по исходному split. Ни одного несовпадения. Validation/test members не извлекались и не читались как measurement payloads. Train SQL — только controller/front/rear; development GNSS — только внешнему scorer.

Исходники/конфигурации повтора взяты из опубликованного commit **4bd4908821e55e08195f08bd88eb7cfab17dc3c7**. Восстановленные research-файлы сверены по Git blob SHA; runtime/core/scorer извлечены из полного проверенного архива, не собраны из excerpts. Config соответствует champion_v8.yaml плюс ровно три измеренных силовых коэффициента; класс GuardedReadoutObserver, output Estimate.v/s, 20 Hz/delay0, readout gain1/holdoff.5, adaptation.5/quarantine1.5 неизменны.

## Это аудит, не новый подбор

Предыдущий PLAN `a7e3436adbb7cfc614d8ea367205103cac8c786c` и pre-IO clarification `64d421436bd5645193ca925308f1ca397408142a` не изменены. Ранее выполнен один profiled fit и один невыбираемый b=0 control. Их опубликованные коэффициенты скопированы без изменения. В этом продолжении **0 global optimizer calls**.

Выполнены один полный paired development replay трёх зафиксированных конфигураций, повтор 56 full-faulted-bag прогонов и контрольные direct baseline/feature-off replay. Также заново вычислены train/check losses при фиксированных theta: тот же набор 700 окон (532 fitting/168 check), без оптимизации глобальных параметров. Для audit loss b вычисляется только как часть прежней функции потерь; это не новая калибровка. least_squares в audit-скрипте заменён запретом вызова.

Все **12 основных development-агрегатов** трёх моделей совпали с прежним отчётом с **delta=0.0**. Все **6 profiled train/check objectives** также совпали с **delta=0.0**. Это воспроизведение тех же данных и конфигураций, не независимый final test.

## Результаты development

17 bags / 7 исходных групп; clean reference в 19 bag/receiver парах, 394221 matched points. Original: 56 scenarios / 60 reference comparisons. Low-speed: 26/34; common-mode: 28/30. Missing reference сохраняется как null, не как нулевая ошибка.

| Метрика | Baseline v8 | H36 profiled | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668142983 | 0.092489880940 | −0.192366% |
| Original fault-event macro RMSE, м/с | 0.237548612056 | 0.193306713057 | **−18.624356%** |
| Pooled clean RMSE, м/с | 0.129305694477 | 0.128871898152 | −0.335481% |
| Scalar-span distance macro RMSE, м | 5.310295004801 | 5.409728932108 | **+1.872475%** |

Предел distance при допуске 1% — 5.363397954849 м. Candidate не проходит. Дополнительный прежний prerequisite также FAIL: profiled check loss **0.177588139339→0.205397654970**, +15.659557% при допуске 0.5%. Причины решения: `aggregate_regression:distance_rmse`, `check_profiled_objective_regression`.

Контроль без nuisance: clean 0.092519508652, original fault 0.241870226182, pooled 0.129024028765 м/с; distance 5.335704345759 м. Он не selectable, и его собственный допуск также не пройден. Более близкая дистанция контроля не разрешает заменить им H36.

H36 изменяет 219424 published velocity ticks в 7 группах; control — 219156. Нет потери coverage, дополнительных false stops или новых individual unrecovered, causal errors/reset. Original unrecovered 4→4. Low-speed event RMSE 0.368545673306→0.312414379251, common-mode 0.100632272301→0.084769886951 м/с; эти выигрыши не заменяют дистанционный допуск.

## Регрессии и ограничения

Original fault RMSE хуже в 33/60 сравнений, clean — в 6/19. `30639_9c362687/rover`, dropout10: **0.258670138631→0.715098344649 м/с**. На master: 0.257095610176→0.711998712346. Семь original recovery замедлились; максимум +0.5 с на `30618_0652866c`, оба receiver.

На полных bags с dropout10 scalar distance macro **6.332766496217→7.180289421013 м**, +13.383139%. Разность published s candidate−baseline на `30618_073f08d1` через 10 с после конца отказа 20.883858 м, к концу bag 21.594596 м. Это дельта алгоритмов, не истинная координатная ошибка. Cropped velocity gain не устраняет интегральную проблему.

Runtime остаётся тем же v8, nuisance b в него не экспортируется. Wheel training targets — псевдоразметка; согласие колёс не доказывает no-slip. Постоянный b может поглощать модельную ошибку; rank условной модели не гарантирует физическую истинность коэффициентов. Дистанционная метрика скалярная, не xyz/ENU.

В новой среде повторно прошли **156 runtime tests + 43 integrity tests + 22 H36 tests**. Наборы H36 включают фактически включённые profiled/control конфигурации. В loss audit сохранён warning `invalid value encountered in subtract` для недоступных начальных stamps (-inf−-inf): эти точки исключаются existing valid-mask; исходный код не правился, все окна/objectives совпали. Синтетика не заменяет измерения.

Fresh enabled installed ROS, оба clock modes, end-to-end latency и node RSS под 2CPU/500MB **NOT_RUN_AFTER_REJECTION**. Прежний remote Actions run36231946468 завершился failure без подтверждённых steps, log404/artifacts[]; причина не установлена. В данном продолжении Actions не перезапускался, зелёный CI не заявляется.

## Уточнение сохранности артефактов

Это дополнение к неизменному REPORT commit **87ae4b33d7128bfe95e767dac7b2f5453c9a2baf**. Его формулировка о приложенном старом local git bundle не описывает фактическую выдачу после смены среды: прежняя рабочая папка, оригинальный bundle и первичные optimizer-логи не сохранились в доступном контейнере и не найдены при поиске файлов. Они не выдуманы и не восстановлены путём нового fit.

Выдаваемый пакет содержит **новые raw-результаты повтора** зафиксированных моделей, новые loss-evaluation NPZ/JSON, data/source receipts, CSV, тестовые логи, exact source/config и patch. Это не оригинальные файлы первой сессии. Старые nfev14/11 и local source SHA62b26b... сохраняются только как исторические сведения опубликованного отчёта. Главный численный вывод теперь дополнительно опирается на доступный полный replay нового архива. Ни нового validation FREEZE, ни final-test результата нет.

## Команды повтора без fitting

Из извлечённого `source/` пакета, после подготовки разрешённых DB в dataset/data:

```bash
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R4/H36 -p 'test_*.py' -v
python research/R4/H36/develop.py --data-root dataset/data \
  --train ../evidence/frozen_models.json --output /tmp/H36-frozen-replay --workers 2
```

Путь output должен быть новым. `fit.py` в этом повторе **не запускать**. Канонический launch не меняется. Для явного экспериментального включения используется `params_file:=.../research/R4/H36/variants/profiled.yaml`; эта инструкция не является заявлением об исполненном ROS benchmark.

Все записи в GitHub — только собственная research/checkpoint-ветка. Merge, auto-merge, force-push и изменения main не выполнялись.
