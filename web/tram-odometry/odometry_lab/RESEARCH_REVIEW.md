# Проверка интеграции и реальный эксперимент, 26.09.2026

## Решение

**Публиковать исправленный исследовательский интерфейс отдельной веткой. Traction-only НЕ продвигать вместо v8.** На целевом 30618 ошибка скорости внутри исходных отказов выросла на 9.9353%. Обычный v8, прежние страницы, numerical kernels, scorer и сохранённые запуски остаются неизменными. PR предназначен для проверки стенда, не для утверждения нового чемпиона.

## Сравнены две реализации

Основа веб-лаборатории: `b134a8898f255b72af9dc085a97de8c6eb010823`, tree `39b7300a933e72efeed39ba404708e96bcfdc19a`. Альтернативная уже опубликованная интеграция: `ce7e635417439aff06cf1ab2f1f817980afa7c5b`. Второй вход: приложенный `tram_web_integration_20260926.zip`.

Выбран ZIP-вариант как основа: он проверяет одинаковые времена публикации, reference, маски и доступность прогнозов, использует закреплённый development split, поддерживает несколько направленных путей. Сравнение только по хешу конфигурации недостаточно. Из подхода ce7 сохранён принцип отдельного верхнего переключателя, но не вторая копия UI/API. Исходные App.tsx и Sidebar.tsx не меняются; оба представления остаются смонтированными.

Из прежних файлов изменяются только catalog.py (регистрация), web/app.py (router до SPA), main.tsx (оболочка) и pyproject.toml (HTML/JS package-data). Старый HackEstimator и все vendor kernels остаются прежними. Фиксированный traction-only задаётся через существующую factory с собственными параметрами с начала replay.

## Исправления до публикации

Первоначальные 61 тест ZIP проходили. Дополнительные проверки выявили непокрытые случаи: позднюю первую и повторную стартовую привязку после сброса, NaN в статусе fix, отсутствие проверки frame, чрезмерную разрешённую поправку, изменяемый исходный документ маршрута, непроверенное членство CSV в запуске, JSON 1e999 и сохранение старой привязки через длинный разрыв. Отдельно добавлена поддержка явно замкнутых путей; её отсутствие было ограничением, не ошибкой старого контракта.

Теперь стартовое окно отсчитывается от начала bag и не переоткрывается. Первые плохие fixes не блокируют всё стартовое окно; до первой привязки ищется допустимый fix, но серия коррекций в этом окне запрещена. После потери/сброса одометрии или разрыва публикации >0.2 с старая привязка недоступна до явного нового replay. Это консервативное инженерное правило, не измеренная характеристика трамвая.

Проверяются конечный допустимый статус, непустой постоянный frame_id, временной порядок до прореживания. Поправка ограничена 5 м, исходный документ копируется, CSV читается одним ограниченным снимком с SHA256. Проверяются membership и уникальность provenance; NaN/Infinity/переполнение JSON отклоняются. Графики разрываются по сегментам. Closed paths поддерживают непрерывную развёрнутую s только при явном совпадении первого/последнего узла.

## Новый реальный native speed-эксперимент

Это исполнение **неизменённого** `research/traction_only/replay.py` из `jabrailkhalil/hack@da3467c3b40900b2e08e933722ef84a09fe44837`. Baseline numerical source `e3b0c9c039d2953fbfcda51231263d38ef9f1024`; активный main `b2783206000091ab11a1c11ac3ff79082188a4fb`. Проверены все 19 исходных pins. Параметры кандидата, scorer, reference masks, fault anchors и пороги после результата не менялись; fitting calls = 0.

Получен development-only GitHub artifact **10902149285**, run **36230833147**. ZIP 29 577 824 байта, SHA256 `418077b219ad6883139c25874ea53c82a60894049528c23764d1c1909b778e85`. Проверены все 17 DB по неизменному split. Полный исходный dataset ZIP здесь не скачивался. Train/validation/final-test payloads не извлекались и не открывались.

Проиграны 17 clean bags, 56 исходных cropped fault-сценариев и те же 56 полных faulted bags, пять фиксированных профилей: v8, traction-only, полный H44, только торможение H44 и off=v8. Оба GNSS-приёмника остаются в метриках, missing не считается нулём. Controller продолжает поступать при отказе колёс. 394221 matched receiver-time samples. Baseline fingerprint совпал точно; off совпадает по массивам и счётчикам.

### Целевой 30618: 12 bags, 229446 matched samples

| Метрика | v8 | Traction-only | Изменение ошибки |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.065329745162 | 0.065395082865 | +0.1000% |
| Original fault-event RMSE, м/с | 0.272398329888 | 0.299461839179 | **+9.9353%** |
| Clean scalar-span distance RMSE, м | 1.080428810576 | 1.074443680960 | -0.5540% |
| Full-faulted distance RMSE, м | 1.227531488049 | 1.228848541477 | +0.1073% |

### Все 17 bags

| Метрика | v8 | Traction-only | Изменение ошибки |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668142983 | 0.092628920140 | -0.0423% |
| Original fault-event RMSE, м/с | 0.237548612056 | 0.234782698746 | -1.1644% |
| Clean scalar-span distance RMSE, м | 5.310295004801 | 5.331529411969 | +0.3999% |
| Full-faulted distance RMSE, м | 6.269376947281 | 6.335833471668 | **+1.0600%** |

30639 отдельно: fault RMSE 0.214315466835 -> 0.191663271791 (-10.5696%), full-faulted distance +1.1410%. Поэтому общий небольшой выигрыш не означает пользу на 30618. На 30618 хуже 14/32 original receiver-case comparisons; на 30639 хуже 2/28. Пример 30618_88548b02/master/dropout10: 0.244553348311 -> 0.519664669195 м/с. Новых false stops нет; четыре прежних неподтверждённых recovery остаются четырьмя, не исключаются.

Кандидат не достигает прежнего минимального 2% clean или 5% original fault gain на общем наборе и превышает 1% full-distance regression. На целевом трамвае существенная fault-регрессия. **DO_NOT_PROMOTE**. Другие controls не переобъявлены selectable победителями.

Это reused development и **native source-clock benchmark**, не receipt-clock replay веб-лаборатории, независимый hidden test или официальный XYZ score. 17 исходных bag ID содержат 15 уникальных DB: замороженный native протокол сохраняет прежний состав, новый web UI исключает повторное взвешивание идентичных DB. Числа этих двух стендов нельзя приравнивать. Distance — scalar-span surrogate, не истинная XYZ-траектория.

## Фактическая проверка веб-кода

После правок **81/81 synthetic/config/API tests PASS** (61 исходный +20 review), включая сохранность прежнего реестра и 500 сравнений ECEF с pyproj. **11/11 Chromium checks PASS**, page errors = 0. Проверены реальный HTML/JS, очередь через mock boundary, сравнение, два графика, журнал, ссылка артефакта, размеры и темы. Браузерные запросы перенаправлены в ASGI TestClient на синтетических данных: это не сетевой HTTP/full React/worker/data test. Python compileall и JavaScript syntax PASS; TypeScript transpile/syntax PASS, не полная React/Vite сборка.

Полный checkout dependency environment, полный прежний test suite, React/Vite build, реальный web-worker на DB, Docker/ROS и ресурсный benchmark не выполнялись. Для native accuracy использован отдельный проверенный source snapshot, а для тестов web — частичный bootstrap ключевых прежних модулей. Непроверенные существующие файлы не заменяются им в Git.

## GNSS и дальнейшие ограничения

Сводка организаторов сохранена как USER_SUPPLIED_ORGANIZER_SUMMARY, исходные сообщения независимо не перепроверены. Официальный Pathgraph/его CRS отсутствуют. Поддержан нормализованный ENU-контракт внешней карты, не угадывание MGRS и не карта из GNSS всей проверяемой поездки. Плечи антенн заданы пользователем; касательная/pitch/roll=0 — приближение. Официальные XY/XYZ, reference point и высота не подтверждены. Поэтому GNSS position accuracy остаётся **NOT_EVALUATED**, а не улучшением на величину innovation.

Low-speed/common-mode, исходный train-check, validation/final-test и enabled ROS для traction-only не выполнялись после отрицательного primary результата. Для стенда требуется последующая проверка полного окружения, а не смягчение критериев ради кандидата.

## Доказательства и повтор

В Git: исходники, тесты, этот отчёт, RESEARCH_REVIEW_VERIFICATION.json и `reports/research_review_20260926/NATIVE_RESULT.json`. Полный raw-пакет ответа `traction_only_native_review_results.zip`: **128578537 байт**, SHA256 **f82a09b67210b1f00e8d55331cf10ba4f7c73e11e76b4ac8487563415e5b3025**. Содержит все native NPZ/JSON, per-case CSV, журнал, receipt и анализ; DB не входят. Это локальный артефакт беседы, не новый Actions artifact.

В полном checkout web-ветки:

```bash
cd odometry_lab
PYTHONPATH=src python -m pytest -q tests/test_research_integration.py tests/test_research_review.py
python scripts/validate_research_ui.py --chromium /usr/bin/chromium --output /tmp/research-ui-fresh
cd frontend
npm ci && npm run build
cd ..
docker compose up -d --build
```

Последние команды являются необходимым полным окружением, не объявлены выполненными. UI: верхняя вкладка «Маршрут и GNSS», hash `#research`.

Native-повтор в точном checkout hack@da3467c3 с подготовленными development DB и research-зависимостями:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research/traction_only/replay.py --run-development --data-root /verified/development --output /new/native-results
```

Не использовать native JSON как готовые результаты web /api/v1/series: форматы/часы различны. Публикация этой ветки не меняет основной профиль и не выполняет merge.
