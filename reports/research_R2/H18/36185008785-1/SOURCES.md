# H18: источники и границы прочитанного

Consensus: первый запрос получил rate limit; повторный узкий поиск Schmidt/consider успешен. Затем фактически выполнен fetch(c9658c437c8754ae8e13cda8d1dcb9eb).

Zanetti, R.; Bishop, R. (2012). *Kalman Filters with Uncompensated Biases*. Journal of Guidance, Control, and Dynamics, 35. Прочитаны metadata и возвращённый вводный текст карточки, НЕ полный текст.
https://consensus.app/papers/kalman-filters-with-uncompensated-biases-zanetti-bishop/c9658c437c8754ae8e13cda8d1dcb9eb/?utm_source=chatgpt

Возвращённый текст описывает учёт коррелированной случайной постоянной ошибки как неопределённости без её оценки в state и связь с Schmidt consider filter. Это мотивация Kd=0 и cross covariance, не подтверждение точности H18 на нашем интерфейсе. Никакие сенсоры/формулы из закрытого полного текста не заимствованы. Поисковая выдача содержит разные данные о диапазоне страниц; здесь диапазон намеренно не утверждается.

Scite: фактически выполнен search_literature по Schmidt/Kalman/consider. Сервис отказал: месячная квота MCP 25 вызовов, reset 2026-10-01 UTC. Metadata/fulltext/citation contexts через Scite НЕ прочитаны. Не куплены статьи или подписки. Упоминания/количество цитирований не трактуются как верификация.

WolframLanguageEvaluator фактически выполнил worksheet wolfram.wl; пять checks True, возвращённые выражения сохранены в wolfram-result.json. Это линейная локальная идеализация, не covariance-certificate нелинейного clipped observer.

Размерности: Pvv m^2/s^2, Pvd m^2/s^3, Pdd m^2/s^4, Qv m^2/s^3, Qd m^2/s^5. Поэтому 2T*Pvd, T^2*Pdd, Qv*T и Qd*T^3 имеют размерность Pvv. Qd не вводится. При отсутствии wheel measurements d и истинное изменение ускорения нельзя независимо идентифицировать. PSD обеспечивает допустимую численную covariance, но не калибровку доверительных интервалов.

История репозитория: v5 отрицательные Qv x2/x4 и слишком быстрая адаптация; v6 projection/decay отрицательные. PR #18/H10 одновременно менял mean d и covariance; H18 mean d не корректирует новым gain. PR #14/#23 задают канонический readout v7 и low-speed protection. PR #26/H11 прочитан как соседний common-mode guard, НЕ включён. Старые результаты не выдаются за сравнение с R2 SHA 65bba39.
