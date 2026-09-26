# Зафиксированный следующий эксперимент

Дата: 2026-09-26. Статус: PREPARED_NOT_EVALUATED. Main не менять.

## Гипотеза и происхождение

Единственный selectable кандидат: v8 + точные torque/power H44 G при исходном max_brake_force_n v8. Baseline commit b2783206000091ab11a1c11ac3ff79082188a4fb, numerical source e3b0c9c039d2953fbfcda51231263d38ef9f1024. H44 source 0ca93500d4d305c21c998bfd8d2a2e78c98b90ad. Значения и все остальные поля фиксированы runtime.py/YAML и не меняются после результатов.

Гипотеза мотивирована уже просмотренными H44/H43 и тремя targeted development cases. Она exploratory: эти случаи не независимый holdout. Это ablation опубликованной калибровки, не новый two-parameter fit. Не требуется заново получать teacher ZIP для воспроизведения фиксированных параметров. Польза GNSS-supervision отдельно не доказывается этим сравнением.

## Порядок

1. Проверить pinned runtime/evaluator/полный профиль и synthetic tests. Сохранить source/config hashes до первого measurement IO.
2. Ровно пять заранее фиксированных профилей: main v8; candidate F/P-only; H44 full G; brake-only G; off=v8. Только candidate выбираемый. Все начинают со своей конфигурацией/предысторией, не перенимают состояние друг друга.
3. Primary development: все 17 bags / 7 групп неизменного split; обе антенны, без очистки reference по ошибке модели. Original four fault types с прежними anchors/crops, controller доступен при wheel dropout. Дополнительно replay каждой инъекции на всём bag; сохраним после восстановления накопленную s. Отсутствие reference = null, не нулевая ошибка. Baseline fingerprint должен совпасть. Число сценариев выводится из данных, не подгоняется под ожидаемое.
4. После primary без retuning: прежние low-speed, abrupt и slow common-mode suites, индивидуальные safety/coverage/recovery, все per-group/leave-one-group-out с раскрытием проигрышей. Повторить train-check на исходных frozen H44 check-окнах, без нового fitting. Недоступный check отмечается INCOMPLETE, не PASS.
5. Только после положительного development/check и отдельного опубликованного freeze разрешать reused validation. Новый final-test сейчас не разрешён. Promotion требует отдельной проверки installed enabled ROS, обоих clocks и ресурсных ограничений.

replay.py реализует этап 3, не выдаёт окончательного решения и не снимает этапы 4-5. Ни одна стадия не переключает default и не выполняет merge.

## Критерии допуска (до новых measurement results)

Clean group-macro, pooled и original fault-event regression <=0.5%; clean и full-faulted scalar-span distance regression <=1%. Нужны >=2% clean либо >=5% original fault improvement. Per-bag clean degradation <=max(0.005 м/с, 5%). Low-speed/abrupt/slow event regression <=0.5%; недоступная проверка не PASS. Никаких новых individual false stops/non-recoveries, потери coverage, нарушений причинности или непредусмотренных reset. Existing missing-reference recovery не удалять из primary.

Train-check aggregate velocity/integral regression <=0.5%, group regression <=5%; это отдельный guard при наличии исходного frozen check cache. Контроль full H44 не должен влиять на допуск основного кандидата: engineering admission сравнивается с v8, научная attribution оформляется отдельно. Не менять пороги/маски/группы после результатов. При отказе сохранить исходный результат; другой вариант требует новой гипотезы/ветки.

Публиковать primary и supplemental metrics отдельно, все локальные проигрыши, retained delta_s faulted-minus-clean (+10 с и terminal), prediction hashes и ошибки integral identity. LOO - sensitivity, не способ выбросить мешающую группу. Никакие group-macro, pooled, cropped/full и validation/development числа не объединять в одну несопоставимую таблицу.

## Ограничения

Согласие GNSS-антенн не делает их независимыми ground truth. Скорость и интегральная дистанция являются proxies; официальный fused XYZ-reference, карта/extrinsics и подтверждённые единицы не появились. Меняется приближение динамики, а не истинная наблюдаемость общего wheel drift. Runtime-кандидат до эксперимента не объявляется улучшившим accuracy.
