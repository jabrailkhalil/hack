# R5-H47 — DEPENDENCY_PENDING / NOT_EVALUATED

**Исследовательский checkpoint, не готов к merge.** Выполнена только H47: проверены исходники и среда, пререгистрирован протокол, реализованы пассивные причинные признаки, отдельный offline-интерфейс меток и запрет выдавать наличие файла за успешную проверку зависимостей. Обученная logistic-модель и вмешательство в веса колёс НЕ реализованы. Измерения точности H47 отсутствуют не из-за отрицательной гипотезы, а из-за недоступных обязательных teacher/atlas payload ZIP.

## 1. Идентичность и сохранность

| Назначение | Значение |
|---|---|
| Baseline R5 | b2783206000091ab11a1c11ac3ff79082188a4fb |
| Полный baseline tree | 973d50d288e050325ee1c71a90fa8d81f2a099af |
| Пререгистрация до H47-тестов/обучения | 49fd44ffd5216526c757b2c9b8eb04a88b07ddce |
| Проверенный source интерфейсов | 56d3db47674d0dd349811f189dd8f12c58c6b9fd |
| Полный tree интерфейсов с baseline | 20142a13116f42e11062fddaf983b42a44e2d8bd |
| Measured runtime candidate / validation freeze | N/A / N/A |
| Ветка | research/R5-H47 |

Полностью сверены все 320 исходных файлов, байты, пути и executable bits. Source ZIP SHA256: 4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4. Отдельный GitHub read подтвердил связь baseline commit с tree. Локальный ZIP не объявляется Git checkout с поддельной ancestry. Прежний R4 snapshot e3b0c9c не используется вместо полного R5.

Фактический baseline — GuardedReadoutObserver с полным champion_v8.yaml/json: 20 Hz, delay0, gain1/holdoff.5, adaptation_tau.5, wheel_time_compensation0, quarantine1.5. Canonical core/readout/Timeline/scorer/config/packaging и старые отчёты не изменены. Новые исходники находятся только в research/R5/H47. Синтетический тест обратного движения использует отдельный экземпляр конфигурации, не новый обучаемый вариант.

PLAN опубликован до разработки и тестов H47. Проверенный локально код затем опубликован; совпадение всего нового Git tree подтверждено независимо локальным вычислением. SHA интерфейса не выдаётся за SHA обученной модели. Merge/auto-merge/force-push не выполнялись.

## 2. Конкретная недостающая зависимость

| Компонент | Необходимый файл | Байты | SHA256 |
|---|---|---:|---|
| H42 teacher | R5_H42_teacher_component.zip | 28190115 | 2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8 |
| H43 atlas | R5_H43_atlas_handoff.zip | 1076521 | 6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011 |

Оба архива искались среди доступных mounts, в Files conversation/Library и полном доступном списке Library ZIP. Через GitHub прочитаны PR56/PR55 и точные H42 R5_HANDOFF_RECEIPT.json / H43 DELIVERY.json. Они связывают файлы с указанными хешами и прямо называют хранилищем conversation attachments, не Actions artifacts; download payload в этих GitHub-квитанциях отсутствует. Не утверждается, что архивы не существуют у авторов; в текущей доступной среде они не получены.

Все 29 записей PACKAGE_MANIFEST нового launch ZIP проверены. Сам manifest указывает teacher_atlas_payloads_included=false. Launch-пакет содержит задания, verifier, contracts и квитанции, но не 85 teacher payload files и 53 atlas payload files. Существующие README/PR/expected.json не заменяют эти данные.

Штатный tools/precheck_components.py реально вызван с ожидаемыми путями: exit2, COMPONENT_TRANSPORT_FAILED на отсутствующем teacher ZIP; каталог извлечения и успешная receipt не созданы. Наш dependency_status.py независимо зарегистрировал MISSING обоих файлов, exit3. DEPENDENCIES.lock.json не создан. Producer-native verifiers и bridge фактических component folds НЕ выполнены. 13 тестов утилит launch используют синтетические ZIP и копии folds координатора; их успех не является native payload verification.

Ранее переданный dataset(4).zip доступен: 256294592 bytes, SHA256 d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52 совпал. В этом проходе H47 проверены только байты архива, SQL/measurement decode и извлечение DB не выполнялись. Датасет не заменяет замороженные teacher/atlas. По инструкции wave2 H42/H43 не перезапускались для их восстановления.

## 3. Что реализовано

CausalFeatureProbe возвращает исходный Estimate без изменения native state и только сохраняет восемь признаков: возраст своего/второго канала, skew, backward rate innovation, model innovation, front-rear mismatch, текущий command mode и среднее прошлых innovations. Нормировки фиксированы baseline, не fitted. Channel ID, bag/group/pose/GNSS/teacher quality не входят в вектор.

Память на канал: <=16 innovation records за <=1 s, предыдущий raw sample и source watermark. Текущий sample исключён из среднего его истории. Дубликаты/старые/будущие/nonfinite samples не добавляются; история стареет на каждом успешном шаге. При недостаточной истории, native rejection, OOD, stale/future command, bootstrap/stop/near-zero — abstention. В частности, собственный признак запрещает timestamp из будущего даже внутри native tolerance 1e-9; native алгоритм при этом не переписан.

Offline TeacherPoint/unique_nearest/proxy_pair_labels — только проверенный синтетически интерфейс, не загрузчик или новая очистка H42. Сравниваются модули wheel speed с teacher magnitude, знак движения из GNSS не придумывается. Только допустимый frozen teacher может стать меткой; оба расходящихся канала, промежуточная ошибка, низкая скорость, missing/tied targets означают abstention. Флаг accepted существует только в offline-модуле, не в сигнатуре признаков. Реального NPZ schema adapter и coverage/fitting pipeline до payload preflight нет.

PLAN фиксирует одну logistic структуру, L2=.01, один bounded solver run без restarts, порог только по fit false-alert budget, отдельный check без настройки и отсутствие synthetic augmentation. До fitting нужны реальные faulty accepted-measurement examples минимум в 3 fit/2 check source groups с заранее заданным минимумом эпизодов/строк. Существование сотен тысяч teacher targets этого не доказывает; такие counts H47 ещё не измерены.

Позднее вмешательство допускается только как снижение веса уже принятого измерения и блокирование его d-learning, с консервативным R и согласованным actual gain/readout. Сейчас вес .25, коэффициенты и threshold не применяются в runtime. Все L-gates и wrong-channel/both-sign/common-bias counterexamples записаны до экспериментов; классификация сама по себе не считается улучшением одометрии.

## 4. Фактически выполненные проверки

| Проверка | Результат |
|---|---|
| Полный исходный unit suite | 161 PASS |
| Исходный research-integrity suite | 43 PASS |
| Новые H47 feature/label/dependency tests | 42 PASS |
| Утилиты wave2 | 13 PASS, не real component preflight |
| Compile src + H47 | PASS |
| Patch на отдельной pristine-копии | PASS, все 8 overlay files совпали |
| Повтор 42 H47 tests после применения patch | PASS; не 42 новых уникальных теста |
| Исходные 320 файлов после работы | Без изменений |
| Native teacher/atlas preflight | NOT_RUN: нет payload ZIP |
| Штатный transport preflight | BLOCKED, exit2 |

В состав 42 тестов входят потактовая точная эквивалентность Estimate и всех полей independent canonical observer на 2500 синтетических шагах; channel permutation; causal prefix; stale/future/duplicates; reset/gap; ограничения истории; self-exclusion; OOD; оба знака label error; common-mode abstention; нельзя передать teacher/GNSS поля в step; presence receipt нельзя назвать DEPENDENCIES.lock.json, перезапись запрещена. Эти проверки не являются реальным training coverage, wrong-channel intervention benchmark или доказательством улучшения RMSE.

WolframLanguageEvaluator выполнил явные формулы: derivative sigmoid, curvature logistic loss >=0, dK/dR<0 при P,R>0, scalar Joseph identity, R inflation не повышает K при том же prior. check.wl и фактический output сохранены. Предшествовавшая автоматическая semantic-context выдача неправильно разобрала символы и не использовалась как oracle. Локальные формулы не доказывают калибровку классификатора или устойчивость всей switched nonlinear системы. Новых Consensus/Scite запросов после известного quota stop нет.

## 5. Результаты, которые отсутствуют

H47 coefficients, fitted threshold, confusion/abstention на реальных fit/check, coverage real faults, clean/fault/pooled/distance RMSE, регрессии, full-distance после recovery, candidate CPU/ROS latency/RSS — N/A. Нулевой эффект пассивного collector в unit-тесте не выдаётся за real-data null result обученной модели. Обученный кандидат не создан; objective calls=0. H47 train/development/validation/final-test не открывались. Новый CI/Actions и installed enabled ROS не запускались; [skip ci] не означает зелёный CI.

Scientific verdict=NOT_EVALUATED; stage=DEPENDENCY_PENDING; source=VERIFIED; data=PARTIAL (dataset есть, обязательных компонентов нет); execution=CHECKPOINTED. Интерфейсные тесты завершены, научное исследование не завершено и не REJECTED. Runtime_verified=false, ready_to_merge=false.

## 6. Воспроизведение и продолжение

На полном checkout source56d3db4 либо verified b278 ZIP с приложенным checkpoint.patch:

```bash
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R5/H47/tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m compileall -q src research/R5/H47
```

Python 3.13.5; NumPy2.3.5/SciPy1.17.0 доступны для старых offline integrity tests, не импортируются passive features. Checkout с интерфейсом уже содержит файлы, повторный git apply не нужен. Вложенные baseline ZIP/launch ZIP в evidence позволяют локально проверить источник; dataset и teacher arrays не включены.

Следующая стадия — получить ДВА указанных payload ZIP, выполнить launch tools/precheck_components.py с раздельными новыми каталогами, оба producer-native verifiers и bridge по фактическим folds, создать новый combined lock. Точные команды и ограничения в research/R5/H47/README.md. Только после этого реализовать чтение verified labels и измерить реальное H47 coverage, затем один fit при достаточном основании. Сохраняются этот PLAN и бюджет; не создавать второй эксперимент или новую очистку teacher. При провале основания не расходовать validation.

Данный patch — воспроизводимый подготовительный интерфейс, НЕ patch доказанного улучшения одометрии. До передачи зависимостей baseline оставить без изменений.
