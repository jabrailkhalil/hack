import { useEffect, useMemo, useState } from "react";
import { api, Artifact, Bag, fmt, Job, Model, Run } from "./types";

const time = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const date = (s: string) => new Date(s).toLocaleString("ru-RU");
const states: Record<string, string> = {
  queued: "В очереди",
  running: "Выполняется",
  succeeded: "Завершено",
  failed: "Ошибка",
  cancelled: "Отменено",
  cancelling: "Отмена…",
  interrupted: "Прервано",
};
const kinds: Record<string, string> = {
  experiment: "Сравнение",
  train: "Обучение",
  tune: "Подбор",
};
const stateClass = (s: string) =>
  "status status-" +
  ((
    { succeeded: "done", failed: "error", cancelling: "running" } as Record<
      string,
      string
    >
  )[s] || s);
type Split = { splits: Record<string, string[]> };

export function DataPage({
  bags,
  onUse,
}: {
  bags: Bag[];
  onUse: (ids: string[]) => void;
}) {
  const [search, setSearch] = useState(""),
    [vehicle, setVehicle] = useState(""),
    [gnss, setGnss] = useState("");
  const [subset, setSubset] = useState("all"),
    [strategy, setStrategy] = useState("chronological");
  const [trainVehicle, setTrainVehicle] = useState("30618"),
    [split, setSplit] = useState<Split | null>(null);
  const [error, setError] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [detail, setDetail] = useState<Bag | null>(null);
  useEffect(() => {
    let active = true;
    setSplit(null);
    setError("");
    api<Split>(`/splits?strategy=${strategy}&train_vehicle=${trainVehicle}`)
      .then((s) => {
        if (active) setSplit(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [strategy, trainVehicle]);
  const filtered = bags.filter(
    (b) =>
      b.id.toLowerCase().includes(search.toLowerCase()) &&
      (!vehicle || b.vehicle === vehicle) &&
      (!gnss || b.has_gnss === (gnss === "yes")) &&
      (subset === "all" || split?.splits[subset]?.includes(b.id)),
  );
  const toggle = (id: string) =>
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id],
    );
  const group = (id: string) =>
    Object.entries(split?.splits || {}).find(([, ids]) =>
      ids.includes(id),
    )?.[0] || "—";
  return (
    <div className="catalog-page">
      <div className="page-tabs">
        {[
          ["all", "Все поездки"],
          ["train", "Train"],
          ["validation", "Validation"],
          ["test", "Test"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={subset === id ? "active" : ""}
            onClick={() => setSubset(id)}
          >
            {label}{" "}
            <small>
              {id === "all" ? bags.length : (split?.splits[id]?.length ?? "…")}
            </small>
          </button>
        ))}
      </div>
      <div className="toolbar">
        <input
          aria-label="Поиск поездок"
          placeholder="Поиск по ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Трамвай"
          value={vehicle}
          onChange={(e) => setVehicle(e.target.value)}
        >
          <option value="">Все трамваи</option>
          {[...new Set(bags.map((b) => b.vehicle))].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
        <select
          aria-label="Наличие GNSS"
          value={gnss}
          onChange={(e) => setGnss(e.target.value)}
        >
          <option value="">Любой GNSS</option>
          <option value="yes">С GNSS</option>
          <option value="no">Без GNSS</option>
        </select>
        <select
          aria-label="Разбиение данных"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
        >
          <option value="chronological">Хронологическое 70/15/15</option>
          <option value="cross_vehicle">Cross-vehicle</option>
        </select>
        {strategy === "cross_vehicle" && (
          <select
            aria-label="Трамвай train"
            value={trainVehicle}
            onChange={(e) => setTrainVehicle(e.target.value)}
          >
            {[...new Set(bags.map((b) => b.vehicle))].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        )}
      </div>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <div className="catalog-body">
        <div className="catalog-list">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="Выбрать найденные поездки"
                    checked={
                      filtered.length > 0 &&
                      filtered.every((b) => selected.includes(b.id))
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [
                              ...new Set([
                                ...selected,
                                ...filtered.map((b) => b.id),
                              ]),
                            ]
                          : selected.filter(
                              (id) => !filtered.some((b) => b.id === id),
                            ),
                      )
                    }
                  />
                </th>
                <th>Поездка</th>
                <th>Трамвай</th>
                <th>Длительность</th>
                <th>GNSS</th>
                <th>Выборка</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((b) => (
                <tr
                  key={b.id}
                  className={
                    "clickable-row " + (detail?.id === b.id ? "selected" : "")
                  }
                  onClick={() => setDetail(b)}
                >
                  <td>
                    <input
                      aria-label={`Выбрать ${b.id}`}
                      type="checkbox"
                      checked={selected.includes(b.id)}
                      onChange={() => toggle(b.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td>
                    <button
                      className="font-mono job-link"
                      onClick={() => setDetail(b)}
                    >
                      {b.id}
                    </button>
                  </td>
                  <td>{b.vehicle}</td>
                  <td className="font-mono">{time(b.duration_s)}</td>
                  <td>
                    <span className="badge">
                      {b.has_gnss ? "GNSS" : "Нет GNSS"}
                    </span>
                  </td>
                  <td>{group(b.id)}</td>
                </tr>
              ))}
              {!filtered.length && (
                <tr>
                  <td colSpan={6} className="empty-state">
                    Поездки не найдены
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <aside className="detail-pane">
          <h2>{detail?.id || "Данные поездок"}</h2>
          {detail ? (
            <>
              <dl>
                <dt>Трамвай</dt>
                <dd>{detail.vehicle}</dd>
                <dt>Длительность</dt>
                <dd>{time(detail.duration_s)}</dd>
                <dt>GNSS</dt>
                <dd>{detail.has_gnss ? "Доступен" : "Отсутствует"}</dd>
                <dt>Выборка</dt>
                <dd>{group(detail.id)}</dd>
              </dl>
              <p className="help mt-4">
                Модели получают два колёсных сигнала и контроллер. GNSS
                используется для оценки и карты.
              </p>
              <button
                className="outline mt-4"
                onClick={() => onUse([detail.id])}
              >
                Использовать в эксперименте
              </button>
            </>
          ) : (
            <p className="help">
              Выберите поездку для просмотра. Дубликаты исключены по
              содержимому; поездки train, validation и test не пересекаются.
            </p>
          )}
        </aside>
      </div>
      <div className="selection-footer">
        <span className="help">
          Выбрано: {selected.length} · Найдено: {filtered.length}
        </span>
        <button
          className="primary"
          disabled={!selected.length}
          onClick={() => onUse(selected)}
        >
          Создать эксперимент →
        </button>
        {selected.length > 0 && (
          <button className="quiet" onClick={() => setSelected([])}>
            Сбросить
          </button>
        )}
      </div>
    </div>
  );
}

const descriptions: Record<string, string> = {
  front: "Скорость по датчику передней тележки.",
  rear: "Скорость по датчику задней тележки.",
  mean: "Среднее доступных свежих колёсных измерений.",
  A: "Устойчивое объединение колёсных измерений с моделью динамики.",
  B: "Адаптивный фильтр Калмана и обучаемая динамика.",
  C: "Адаптивный EKF с обучаемой остаточной поправкой.",
  H1: "Перенос измерений во времени с учётом возраста сигнала.",
  H2: "Обработка поздних измерений с историей состояний.",
  hack_v5: "Адаптивное ядро hack v5.",
  hack_v6: "Выравнивание времени измерений, профиль v6.",
  hack_v7: "Защищённый выход оценки, профиль v7.",
  hack_v8: "Зафиксированный профиль champion v8.",
};
export function ModelsPage({
  models,
  artifacts,
  onUse,
}: {
  models: Model[];
  artifacts: Artifact[];
  onUse: (
    id: string,
    target: "experiment" | "train" | "tune",
    artifact?: string,
  ) => void;
}) {
  const [tab, setTab] = useState("catalog"),
    [selected, setSelected] = useState("A");
  const model = models.find((m) => m.id === selected);
  return (
    <div className="catalog-page">
      <div className="page-tabs">
        <button
          className={tab === "catalog" ? "active" : ""}
          onClick={() => setTab("catalog")}
        >
          Каталог моделей <small>{models.length}</small>
        </button>
        <button
          className={tab === "versions" ? "active" : ""}
          onClick={() => setTab("versions")}
        >
          Сохранённые версии <small>{artifacts.length}</small>
        </button>
      </div>
      {tab === "catalog" ? (
        <div className="catalog-body">
          <div className="catalog-list card-list">
            {["Базовые", "Исследовательские", "Hack"].map((group, index) => (
              <section key={group}>
                <h3 className="help mb-2">{group}</h3>
                <div className="flex flex-col gap-2">
                  {models
                    .filter((m) =>
                      index === 0
                        ? ["front", "rear", "mean"].includes(m.id)
                        : index === 2
                          ? m.id.startsWith("hack")
                          : !["front", "rear", "mean"].includes(m.id) &&
                            !m.id.startsWith("hack"),
                    )
                    .map((m) => (
                      <div
                        key={m.id}
                        className={
                          "catalog-card " + (selected === m.id ? "active" : "")
                        }
                      >
                        <button
                          className="w-full text-left justify-between"
                          onClick={() => setSelected(m.id)}
                        >
                          <span className="text-[13px] font-medium">
                            {m.label}
                          </span>
                          <span className="badge">
                            {m.training
                              ? "Обучаемая"
                              : index === 0
                                ? "Baseline"
                                : "Подбор параметров"}
                          </span>
                        </button>
                        <p>{descriptions[m.id] || m.label}</p>
                        {selected === m.id && (
                          <div className="button-row">
                            <button
                              className="outline"
                              onClick={() => onUse(m.id, "experiment")}
                            >
                              Использовать в эксперименте
                            </button>
                            <button
                              className="outline"
                              onClick={() => onUse(m.id, "tune")}
                            >
                              Подобрать параметры
                            </button>
                            {m.training && (
                              <button
                                className="outline"
                                onClick={() => onUse(m.id, "train")}
                              >
                                Обучить
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                </div>
              </section>
            ))}
            <div className="catalog-card">
              <h3>D · геометрия маршрута</h3>
              <p>
                Отдельный геометрический модуль. Не является моделью скорости.
              </p>
            </div>
          </div>
          <aside className="detail-pane">
            <h2>{model?.label || "Выберите модель"}</h2>
            {model && (
              <>
                <p className="help">{descriptions[model.id]}</p>
                <h3 className="mt-5 mb-2">Параметры по умолчанию</h3>
                <table>
                  <thead>
                    <tr>
                      <th>Параметр</th>
                      <th>Значение</th>
                    </tr>
                  </thead>
                  <tbody>
                    {model.parameters.map((p) => (
                      <tr key={p.name}>
                        <td className="break-all">
                          {p.name}
                          <small className="block">{p.unit}</small>
                        </td>
                        <td className="font-mono">{String(p.default)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {model.aliases.length > 0 && (
                  <>
                    <h3 className="mt-5">Происхождение</h3>
                    <p className="help mt-2">{model.aliases.join(", ")}</p>
                  </>
                )}
                <a
                  className="block mt-4 text-[11px]"
                  href="/api/v1/models"
                  target="_blank"
                  rel="noreferrer"
                >
                  Каталог и контрольные суммы JSON ↗
                </a>
              </>
            )}
          </aside>
        </div>
      ) : (
        <div className="catalog-list">
          <table>
            <thead>
              <tr>
                <th>Версия</th>
                <th>Базовая модель</th>
                <th>Создано</th>
                <th>Происхождение</th>
                <th>RMSE, м/с</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{a.model_id}</td>
                  <td>{date(a.created)}</td>
                  <td>{kinds[a.kind] || a.kind}</td>
                  <td className="font-mono">
                    {fmt(a.validation?.aggregate?.pooled_speed?.rmse_mps)}
                  </td>
                  <td>
                    <div className="button-row">
                      <button
                        className="outline"
                        onClick={() => onUse(a.model_id, "experiment", a.id)}
                      >
                        Использовать
                      </button>
                      <a
                        href={"/api/v1/artifacts/" + a.id}
                        target="_blank"
                        rel="noreferrer"
                      >
                        JSON
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
              {!artifacts.length && (
                <tr>
                  <td colSpan={6} className="empty-state">
                    Обучите модель или выполните подбор, чтобы сохранить новую
                    версию.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ExperimentsPage({
  jobs,
  runs,
  selected,
  onToggle,
  expanded,
  onExpand,
  onRetry,
  onCancel,
  onShow,
}: {
  jobs: Job[];
  runs: Run[];
  selected: string[];
  onToggle: (id: string) => void;
  expanded: string;
  onExpand: (id: string) => void;
  onRetry: (job: Job) => void;
  onCancel: (job: Job) => void;
  onShow: (ids?: string[]) => void;
}) {
  const [tab, setTab] = useState("jobs"),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState("");
  const job = jobs.find((j) => j.id === expanded);
  const common = useMemo(() => {
    const chosen = runs.filter((r) => selected.includes(r.id));
    return (
      chosen[0]?.metrics.bags
        .filter((b) =>
          chosen.every((r) => r.metrics.bags.some((x) => x.id === b.id)),
        )
        .map((b) => b.id) || []
    );
  }, [runs, selected]);
  const filtered = jobs.filter(
    (j) =>
      (!status || j.status === status) &&
      `${j.request.name || ""} ${j.id} ${j.request.models?.map((m: any) => m.id)}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const filteredRuns = runs.filter((r) =>
    r.id.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="catalog-page">
      <div className="page-tabs">
        <button
          className={tab === "jobs" ? "active" : ""}
          onClick={() => setTab("jobs")}
        >
          Задания <small>{jobs.length}</small>
        </button>
        <button
          className={tab === "runs" ? "active" : ""}
          onClick={() => setTab("runs")}
        >
          Сохранённые запуски <small>{runs.length}</small>
        </button>
      </div>
      <div className="toolbar">
        <input
          aria-label="Поиск экспериментов"
          placeholder="Поиск…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {tab === "jobs" && (
          <select
            aria-label="Статус задания"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Все статусы</option>
            {Object.entries(states).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        )}
        <span className="help">Выбрано запусков: {selected.length}</span>
        <button
          className="outline"
          disabled={!common.length}
          onClick={() => onShow()}
        >
          Сравнить выбранные →
        </button>
      </div>
      <div className="catalog-body">
        <div className="catalog-list">
          {tab === "jobs" ? (
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>Название</th>
                  <th>Тип</th>
                  <th>Модели</th>
                  <th>Создано</th>
                  <th>Статус</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((j) => (
                  <tr
                    key={j.id}
                    className={expanded === j.id ? "selected" : ""}
                  >
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Выбрать запуски ${j.request.name || j.id}`}
                        disabled={!j.result?.runs?.length}
                        checked={
                          !!j.result?.runs?.length &&
                          j.result.runs.every((id) => selected.includes(id))
                        }
                        onChange={(e) =>
                          j.result?.runs?.forEach((id) => {
                            if (selected.includes(id) !== e.target.checked)
                              onToggle(id);
                          })
                        }
                      />
                    </td>
                    <td>
                      <button
                        className="job-link"
                        onClick={() => onExpand(expanded === j.id ? "" : j.id)}
                      >
                        {j.request.name || j.id.slice(0, 8)}
                      </button>
                    </td>
                    <td>{kinds[j.kind] || j.kind}</td>
                    <td>
                      {j.request.models?.map((m: any) => m.id).join(", ")}
                    </td>
                    <td className="whitespace-nowrap text-[11px]">
                      {date(j.created)}
                    </td>
                    <td>
                      <span className={stateClass(j.status)}>
                        {states[j.status] || j.status}
                      </span>
                    </td>
                    <td>
                      <button className="quiet" onClick={() => onExpand(j.id)}>
                        Подробнее
                      </button>
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={7} className="empty-state">
                      Заданий нет. CLI-результаты доступны на вкладке
                      сохранённых запусков.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>Запуск</th>
                  <th>Поездок</th>
                  <th>RMSE, м/с</th>
                  <th>Покрытие</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Выбрать ${r.id}`}
                        checked={selected.includes(r.id)}
                        onChange={() => onToggle(r.id)}
                      />
                    </td>
                    <td>
                      <span>{r.id.split("/").pop()}</span>
                      <small className="block break-all">{r.id}</small>
                    </td>
                    <td>{r.metrics.bags.length}</td>
                    <td className="font-mono">
                      {fmt(r.metrics.aggregate.pooled_speed.rmse_mps)}
                    </td>
                    <td>{fmt(r.metrics.aggregate.coverage * 100, 1)}%</td>
                    <td>
                      <button className="quiet" onClick={() => onShow([r.id])}>
                        Анализ →
                      </button>
                    </td>
                  </tr>
                ))}
                {!filteredRuns.length && (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      Запуски не найдены
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {tab === "jobs" && job && (
          <aside className="detail-pane">
            <div className="card-top">
              <h2>{job.request.name || "Задание"}</h2>
              <button
                aria-label="Закрыть детали"
                className="quiet"
                onClick={() => onExpand("")}
              >
                ×
              </button>
            </div>
            <dl>
              <dt>Статус</dt>
              <dd>{states[job.status]}</dd>
              <dt>Тип</dt>
              <dd>{kinds[job.kind]}</dd>
              <dt>Seed</dt>
              <dd>{job.request.seed ?? 42}</dd>
            </dl>
            {job.error && <p className="error-banner mt-4">{job.error}</p>}
            <h3 className="mt-5">Журнал</h3>
            <pre>{job.log || "Ожидание worker…"}</pre>
            <details>
              <summary className="cursor-pointer">Конфигурация JSON</summary>
              <pre>{JSON.stringify(job.request, null, 2)}</pre>
            </details>
            <div className="button-row">
              {["queued", "running"].includes(job.status) ? (
                <button
                  className="outline danger"
                  onClick={() => onCancel(job)}
                >
                  Отменить задание
                </button>
              ) : (
                <button className="outline" onClick={() => onRetry(job)}>
                  Повторить
                </button>
              )}
              {!!job.result?.runs?.length && (
                <button
                  className="primary"
                  onClick={() => onShow(job.result!.runs!)}
                >
                  Открыть результаты →
                </button>
              )}
            </div>
          </aside>
        )}
      </div>
      <div className="selection-footer">
        <span className="help">
          {selected.length
            ? common.length
              ? `Общих поездок: ${common.length}`
              : "Нет общих поездок для сравнения"
            : "Отметьте запуски для совместного анализа."}
        </span>
      </div>
    </div>
  );
}
