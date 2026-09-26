# Каталог допуска к выбору main

Источник первичного снимка: Actions 36230125875, 110 веток и 40 PR на момент выгрузки. Это обзор вердиктов и исходников, **не повторный численный запуск каждого исторического исследования**. Свежие числа в REPORT.md относятся к прямому девятимодельному сравнению.

## Прямо сравненные реализации

Пять оценивателей godknows1337 из experiments/tram-a, tram-b, tram-c, tram-h01, tram-h02: реально исполнены A/B/C/H1_10/H2_050 плюс mean/front/rear на одинаковых 19 validation-bag и 152 fault-сценариях. Все пять не прошли условия замены текущего v8. D — только известная геометрия; 802 координатных точки совпали, новая скорость/реальная карта не оценивалась. Точные SHA в REPORT.md/FREEZE.json.

## Исторические этапы

- PR #6–#12: прежние baseline/калибровки/сдача; старый v4 final test не является новым тестом выбранного v8.
- PR #13 и #14: low-speed lock и guarded readout, уже вошедшие в v7/v8 через #23. Не считать дополнительными независимыми финальными моделями.
- PR #23/#26: интегрированный v7 и последующий v8; текущий неизменный numerical baseline.
- PR #15–#22, #24, #25, #27: отрицательные исследования R1/H13. Их source, метрики, регрессии и несработавшие механизмы остаются в ветках; они не дают готового eligible replacement.

## R2

| PR | Исследование | Сохранённый вердикт |
|---|---|---|
| #28 | H12 integral readout | REJECTED |
| #29 | H13 interval disturbance | REJECTED |
| #30 | H17 command delay | REJECTED |
| #31 | H14 asynchronous adaptation | INCONCLUSIVE, отсутствует подтверждённое покрытие |
| #32 | H19 sequential channel detector | REJECTED, неверный выбор канала |
| #33 | H15 torque-change correction | REJECTED |
| #34 | H16 multi-horizon physics | REJECTED: fault gain 6.83%, но distance regression 1.18% выше допуска |
| #35 | H20 asymmetric wheels | REJECTED |
| #36 | H21 veto | INCONCLUSIVE |
| #37/#38 | H18 covariance | REJECTED |

## R3 и новые параллельные ветки

| PR | Исследование | Сохранённый вердикт |
|---|---|---|
| #39 | H27 committed disturbance | REJECTED на development |
| #40 | H22 bias-constrained identification | IN_PROGRESS на момент снимка; готовый победитель не подтверждён |
| #41 | H25 relative wheel scale | INCONCLUSIVE |
| #42 | H26 innovation correlation | INCONCLUSIVE |
| #43 | H23 outage-only H16 | REJECTED: fault regression |
| #44 | H30 native-time correction | REJECTED |
| #45 | H24 monotone command map | REJECTED |

После первичного снимка отдельно прочитаны новые PR **lifefire1**: #46 (R4-H37 traction/power ordering) — NOT_EVALUATED, completed train foundation не является accuracy gain; #47 (R4-H33 diagnostic GLS) — NOT_EVALUATED, runner не был выделен, runtime-кандидат не создан. Ни один не готов к merge. Остальные недавно созданные R4 branches без завершённого сопоставимого отчёта не объявлены проверенными конкурентами.

Статусы относятся к прочитанным версиям, а не гарантируют неизменность будущих branches. Новый eligible результат должен сравниваться с выбранным v8 отдельно. Не удалять чужие ветки, не смешивать патчи с индивидуальными метриками и не считать успех исследовательского workflow доказательством улучшения.
