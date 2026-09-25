# H12: источники, прочитанные материалы и ограничения

Основной источник гипотезы — конкретный baseline 65bba39ed05c781f3f69a65c02f69931152cbfd9: core.py, guarded_readout.py, Timeline, guarded_node, canonical launch/profile, evaluate.py, experiment.Store и score/match, research_guarded.compare, research_v6.compare. Проверены новые source hashes; исторические pins не изменены.

Изучены полные описания PR #14/#23 (output-only readout и low-speed защита), #21/H01 (отрицательная внутренняя компенсация), #25/H08 (отрицательная замена внутреннего numerical predictor), #26/H11 (соседняя quarantine, НЕ включена в baseline). Отрицательные H02/#15 и v6 projection/decay изучены в предыдущем задании; их результаты относятся к старому baseline, не R2. Другие R2 validation-результаты не использованы.

## Внешняя литература

[1] Guarro M., Ferrante F., Sanfelice R.G. A hybrid observer for linear systems under delayed sporadic measurements. International Journal of Robust and Nonlinear Control 34(10), 6610–6635 (2024). DOI: 10.1002/rnc.7213.
https://onlinelibrary.wiley.com/doi/10.1002/rnc.7213

Consensus: узкий поиск delayed measurements/output prediction; fetch id 1930bef119f95c7b99f851bae4728936 вернул abstract и metadata. Scite: metadata, 3 term-matched excerpts и первые 6500 из 26383 символов body, source=fulltext. Это фрагмент полного текста, НЕ прочитанная целиком статья; извлечённый текст утрачивает часть формул. Прочитаны постановка времён sampling/arrival, intro о variable delays и bounded memory. Рассматривается иной гибридный observer; его теоремы не доказывают точность H12. Scite показал mentioning-контекст ссылок; это не независимая проверка наших результатов. Preprint 10.22541/au.169105690.09923369/v1 исключён как дубликат журнальной версии.

В качестве соседней работы найден Kim, Kang, Ahn, Delay-Compensated Lane-Coordinate Vehicle State Estimation Using Low-Cost Sensors (Sensors 2025, 25(19), 6251), DOI 10.3390/s25196251, https://www.mdpi.com/1424-8220/25/19/6251. Прочитаны только abstract/metadata; метод camera/IMU/steering исключён из реализации из-за несовместимого интерфейса.

## Wolfram

Выполнены два вызова WolframLanguageEvaluator; worksheet и фактический вывод сохранены рядом. Первый вернул j*h^2/2, j*h^2/(2*n), partial-cell j*ell^2/2, предел 0, constant-acceleration error 0, average-integrals minus integral(mean stamp) = -j*(h1-h2)^2/8; units m/s. Первая попытка FullSimplify не доказала convex bound (неравенство осталось unevaluated), с warnings. Второй Reduce поиска контрпримера convex bound вернул False.

При Lipschitz ускорении и right-endpoint значениях bound на каждой пересечённой ячейке L*ell^2/2, суммарно <=L*h*Delta_max/2. Это условный bound квадратуры; actual a_model может иметь скачки и не равен истинному ускорению. Кусочно-постоянный интеграл выбранной дискретной истории точен по определению. Текущий model segment становится известен только в конце predictor step; он не объявляется ранее измеренной траекторией.

Величина readout correction ограничена существующим max_accel*max_age; convex recursion не усиливает bounded increment при 0<=K,g<=1. K=0 не даёт строгого сжатия. Ограниченная скорость поправки НЕ гарантирует ограниченность накопленной ошибки дистанции. Общая колёсная ошибка и model mismatch без внешнего эталона не идентифицируются. Ни аналитика, ни цитируемые статьи не заменяют измерение на разрешённых реальных записях.
