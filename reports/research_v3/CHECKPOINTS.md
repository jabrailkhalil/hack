# Сохранённые этапы v3

Промежуточные результаты сохранялись отдельно от принятия новой конфигурации в main.

| Этап | Commit / проверка |
|---|---|
| Подготовка исходников и датасета с checksum | `0aec92433455cf7958ba9f2318a0ab1c7012cee1` |
| План эксперимента, списки разделов и критерии принятия до fitting | `112a60173d838915665462369d0351c7f7c6c38e` |
| Fitter, metadata-only группировка, evaluator, тесты и workflow | `16d9f6ffd5f9d59cc1821a85eb690a2680be0994` |
| Промежуточная сводка локального запуска | [dca0d50](https://github.com/jabrailkhalil/hack/commit/dca0d50210075fb4ff45d0d92b4316695335c470), ветка `checkpoint/calibration-v3-local` |
| Полный повтор исследования на GitHub, все JSON/CSV, split и YAML | [a5ca8f8](https://github.com/jabrailkhalil/hack/commit/a5ca8f893b5d12b6dc1ff73470484d0299dac7ed) |
| Проверка выбранного calibrated default в настоящем ROS launch | [6057311](https://github.com/jabrailkhalil/hack/commit/6057311f7768a076bfa53d34b3d3e9919c08bd60) |

Исследовательский workflow: https://github.com/jabrailkhalil/hack/actions/runs/36154211683 — experiment и publish завершились success. Локальные и remote-результаты выбрали одну и ту же `balanced_physics`, округлённые метрики совпадают; последние разряды некоторых fitted-коэффициентов зависят от вычислительной среды.

ROS/source CI: https://github.com/jabrailkhalil/hack/actions/runs/36154901770 — core, research-integrity, ros-humble, offline-limited завершились success. В core пройдено 35 тестов. Проверялись и прежний адаптер, и отдельно запускаемый calibrated default под 2 CPU / 512 MiB без сети после подготовки окружения.

Checkpoint-ветка сохранена без объединения в рабочую во время активного исследования: это не изменяло SHA, на котором workflow защищает публикацию от перезаписи чужих изменений. Основные результаты находятся в `reports/research_v3/` рабочей ветки и включаются в PR вместе с источниками.

Final test: 22 bag не использованы в fitting/evaluation. Это сохранение промежуточной работы и завершение validation-цикла, не отправка решения на платформу.
