# Прочитанные источники и границы переноса

## Научная работа
Zhaoxia Huang. Application of interval state estimation in vehicle control. Alexandria Engineering Journal 61(1), 911–916, January 2022. DOI 10.1016/j.aej.2021.04.074. Publisher abstract: https://www.sciencedirect.com/science/article/pii/S1110016821003173 . Дата online/search metadata 2021 отличается от выпуска 2022.

Consensus: узкий title-search выполнен, paper ID aed469e364a55edf9b4559529f34e3d8, затем fetch. Search вернул abstract LPV observer, turning/cornering/driving changes, simulation; fetch отдельно вернул metadata и «Abstract not available». Не прочитан полный текст. Canonical record: https://consensus.app/papers/application-of-interval-state-estimation-in-vehicle-huang/aed469e364a55edf9b4559529f34e3d8/?utm_source=chatgpt . Citation count 9 — snapshot сервиса, не независимая верификация.

Scite search_literature по DOI реально вызван. Ответ: «You have reached your monthly MCP usage limit (25 calls). Your usage resets on 2026-10-01 (UTC).» Metadata/fulltext/citation context недоступны, не подменены выдуманным Scite-анализом. Покупок/изменения подписки не было.

Abstract издателя прочитан отдельно через web. Работа — только ориентир класса interval-estimation/fault detection: другая модель и симуляции. Нельзя из неё вывести наши wheel-only bounds, реальную точность, универсальное обнаружение common bias или независимый выигрыш.

## Проект: прочитаны именно указанные версии
- Core/guarded_readout/Timeline/configs/evaluate/experiment/roles: 65bba39ed05c781f3f69a65c02f69931152cbfd9.
- reports/research_v6/REPORT.md: отрицательные projection/decay, неизменные thresholds; был прочитан в H08, сохранён в baseline.
- H08/PR25: прежнее точное интегрирование при том же v5 не улучшило accuracy, fault +.588397%; это НЕ сравнение с R2.
- H02/PR15: R(age,skew) не дало required gain; без 1/N, common-mode ограничение. Наш метод не меняет R.
- H06/PR16: нулевое покрытие REACQUIRING на исходной suite и synthetic common-mode regression. Не повторять ошибку: проверить активацию ДО validation, не ускорять recovery.
- H10/PR18: joint [v,d] ухудшил fault, uncertainty не калибрована. Здесь основной observer/covariance не заменяется.
- PR14: output-only guarded readout, внутренний v5 отдельно от published Estimate, development до validation.
- PR23: canonical v7 + low-speed common zero-lock guard, merge baseline 65bba39... .
- PR26/H11: соседняя quarantine abrupt common RATE_ANOMALY, read-only ознакомление. Код не переносится, его цифры не используются для подбора H21.

Не читались результаты validation других исследователей R2 для выбора параметров. Один априорный кандидат, без fitting. Wolfram actual worksheet/output рядом; observational rank=2 показывает (v+k,b-k) неразличимость, отсутствие возможности обнаружить произвольное постоянное common bias без дополнительного допущения. Model/anchor assumptions явно условные.
