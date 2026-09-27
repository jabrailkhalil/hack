import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronDown,
  Clock3,
  Gauge,
  GitBranch,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Settings2,
  SkipBack,
  TrainFront,
  X,
} from "lucide-react";
import MapPanel from "./MapPanel";
import Charts from "./Charts";
import Sidebar, { type Section } from "./components/Sidebar";
import { DataPage, ModelsPage, ExperimentsPage } from "./CatalogPages";
import TripPicker from "./TripPicker";
import SplitPicker from "./SplitPicker";
import {
  api,
  Artifact,
  Bag,
  colors,
  fmt,
  Geometry,
  Job,
  Model,
  post,
  Run,
  Series,
} from "./types";

const topicNames: Record<string, string> = {
  both: "Обе тележки",
  "/vehicle/front_bogie_velocity": "Передняя тележка",
  "/vehicle/rear_bogie_velocity": "Задняя тележка",
  "/vehicle/driver_position_cmd": "Контроллер",
};
type Fault = {
  kind: string;
  topic: string;
  start_s: number;
  end_s: number;
  value: number;
  probability: number;
};
type Panel = "experiment" | "train" | "tune" | "history" | null;
const stamp = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export default function App() {
  const [page, setPage] = useState<Section>("analysis");
  const [chartMode, setChartMode] = useState<"all" | "speed" | "path" | "diag">(
    "all",
  );
  const [extraMetrics, setExtraMetrics] = useState(false);
  const [connected, setConnected] = useState(false);
  const [models, setModels] = useState<Model[]>([]),
    [bags, setBags] = useState<Bag[]>([]),
    [runs, setRuns] = useState<Run[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]),
    [bag, setBag] = useState(""),
    [series, setSeries] = useState<Series[]>([]),
    [geometry, setGeometry] = useState<Geometry | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [cursor, setCursor] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [hidden, setHidden] = useState<Set<string>>(new Set()),
    [zoom, setZoom] = useState<[number, number]>([0, 100]),
    [diagnostic, setDiagnostic] = useState("");
  const [panel, setPanel] = useState<Panel>(null),
    [expandedJob, setExpandedJob] = useState(""),
    [busy, setBusy] = useState(false);
  const [chosen, setChosen] = useState(["mean", "A"]),
    [params, setParams] = useState<Record<string, string>>({}),
    [weightIds, setWeightIds] = useState<Record<string, string>>({});
  const [selectionMode, setSelectionMode] = useState("bags"),
    [chosenBags, setChosenBags] = useState<string[]>([]),
    [split, setSplit] = useState("chronological"),
    [subset, setSubset] = useState("validation"),
    [vehicle, setVehicle] = useState("30618"),
    [seed, setSeed] = useState(42),
    [name, setName] = useState("");
  const [faults, setFaults] = useState<Fault[]>([]),
    [ranges, setRanges] = useState(
      '{\n  "wheel_scale": {"min": 0.27, "max": 0.285}\n}',
    ),
    [budget, setBudget] = useState(24),
    [coverage, setCoverage] = useState(95),
    [quality, setQuality] = useState("{}");
  const [trainingSelection, setTrainingSelection] = useState({
    train_bags: [] as string[],
    validation_bags: [] as string[],
  });
  const finished = useRef(new Set<string>());
  const initialized = useRef(false);
  const refresh = async () => {
    const [r, j, a] = await Promise.all([
      api<Run[]>("/runs"),
      api<Job[]>("/jobs"),
      api<Artifact[]>("/artifacts"),
    ]);
    setConnected(true);
    setRuns(r);
    setJobs(j);
    setArtifacts(a);
    return { r, j };
  };
  useEffect(() => {
    Promise.all([
      api<{ models: Model[] }>("/models"),
      api<{ bags: Bag[] }>("/dataset"),
      refresh(),
    ])
      .then(([m, d, { r, j }]) => {
        setModels(m.models);
        setBags(d.bags);
        const first = r.find((x) => x.metrics.bags.length);
        if (first) {
          setSelectedRuns([first.id]);
          setBag(first.metrics.bags[0].id);
        }
        const defaultBag =
          d.bags.find((x) => x.id === "30618_0e41eac3") ||
          d.bags.find((x) => x.has_gnss);
        if (defaultBag) setChosenBags([defaultBag.id]);
        j.forEach((x) => finished.current.add(x.id + ":" + x.status));
      })
      .catch((e) => setError(e.message))
      .finally(() => {
        initialized.current = true;
        setLoading(false);
      });
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!initialized.current) return;
      api<Job[]>("/jobs")
        .then(async (next) => {
          setConnected(true);
          setJobs(next);
          for (const job of next) {
            const key = job.id + ":" + job.status;
            if (job.status === "succeeded" && !finished.current.has(key)) {
              finished.current.add(key);
              const fresh = await refresh();
              if (job.kind === "experiment" && job.result?.runs?.length) {
                setSelectedRuns(job.result.runs);
                const r = fresh.r.find((r) => r.id === job.result!.runs![0]);
                if (r) setBag(r.metrics.bags[0].id);
              }
            }
          }
        })
        .catch(() => setConnected(false));
    }, 2000);
    return () => clearInterval(timer);
  }, []);
  const availableBags = useMemo(() => {
    const selected = runs.filter((r) => selectedRuns.includes(r.id));
    if (!selected.length) return [];
    return selected[0].metrics.bags
      .filter((b) =>
        selected.every((r) => r.metrics.bags.some((x) => x.id === b.id)),
      )
      .map((b) => b.id);
  }, [runs, selectedRuns]);
  useEffect(() => {
    if (availableBags.length && !availableBags.includes(bag))
      setBag(availableBags[0]);
  }, [availableBags, bag]);
  useEffect(() => {
    if (!bag || !selectedRuns.length || !availableBags.includes(bag)) {
      setLoading(false);
      setSeries([]);
      setGeometry(null);
      return;
    }
    let active = true;
    setLoading(true);
    setPlaying(false);
    Promise.all([
      Promise.all(
        selectedRuns.map((run) =>
          api<Series>(
            `/series?run=${encodeURIComponent(run)}&bag=${encodeURIComponent(bag)}`,
          ),
        ),
      ),
      api<Geometry>("/geometry/" + bag),
    ])
      .then(([data, geo]) => {
        if (!active) return;
        setSeries(data);
        setGeometry(geo);
        setCursor(data[0]?.t[0] || 0);
        setZoom([0, 100]);
        setHidden(new Set());
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          setSeries([]);
          setGeometry(null);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [bag, selectedRuns, availableBags]);
  const start = series[0]?.t[0] || 0,
    end = series[0]?.t.at(-1) || 0;
  useEffect(() => {
    if (!playing) return;
    let prev = performance.now();
    const timer = setInterval(() => {
      const now = performance.now(),
        dt = (now - prev) / 1000;
      prev = now;
      setCursor((c) => {
        if (c + dt * speed >= end) {
          setPlaying(false);
          return end;
        }
        return c + dt * speed;
      });
    }, 70);
    return () => clearInterval(timer);
  }, [playing, speed, end]);
  const open = (next: Panel) => {
    setError("");
    setPage("analysis");
    setPanel(next);
    if (next === "train") {
      const id =
        chosen.find((id) => models.find((m) => m.id === id)?.training) || "A";
      setChosen([id]);
    }
    if (next === "tune") setChosen([chosen[0] || "mean"]);
  };
  const toggleModel = (id: string) => {
    if (panel === "train" || panel === "tune") setChosen([id]);
    else
      setChosen((x) =>
        x.includes(id) ? x.filter((v) => v !== id) : [...x, id],
      );
  };
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      if (!chosen.length) throw new Error("Выберите модель");
      if (
        panel === "experiment" &&
        selectionMode === "bags" &&
        !chosenBags.length
      )
        throw new Error("Выберите поездку");
      const kind =
        panel === "train" ? "train" : panel === "tune" ? "tune" : "experiment";
      const request = {
        name,
        ...(kind !== "experiment" ? trainingSelection : {}),
        models: chosen.map((id) => ({
          id,
          parameters: JSON.parse(params[id] || "{}"),
          artifact: weightIds[id] || undefined,
        })),
        bags:
          kind === "experiment" && selectionMode === "bags" ? chosenBags : [],
        split,
        subset,
        train_vehicle: vehicle,
        seed,
        quality: JSON.parse(quality),
        faults: faults.map((f) => ({
          kind: f.kind,
          topics:
            f.topic === "both"
              ? [
                  "/vehicle/front_bogie_velocity",
                  "/vehicle/rear_bogie_velocity",
                ]
              : [f.topic],
          start_s: f.start_s,
          end_s: f.end_s,
          probability: f.probability,
          ...(f.kind === "delay"
            ? { delay_s: f.value }
            : f.kind === "scale"
              ? { factor: f.value }
              : f.kind === "spike"
                ? { amplitude: f.value }
                : {}),
        })),
        ...(kind === "tune"
          ? {
              ranges: JSON.parse(ranges),
              budget,
              coverage_floor: coverage / 100,
            }
          : {}),
      };
      const job = await post<Job>("/jobs", { kind, request });
      setJobs((x) => [job, ...x]);
      setExpandedJob(job.id);
      setPanel("history");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const replayJob = async (job: Job) => {
    try {
      const created = await post<Job>("/jobs", {
        kind: job.kind,
        request: job.request,
      });
      setJobs((j) => [created, ...j]);
      setExpandedJob(created.id);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const compare = (id: string) => {
    setSelectedRuns((ids) =>
      ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id],
    );
  };
  const diagnosticNames = Array.from(
    new Set(series.flatMap((s) => Object.keys(s.diagnostics))),
  );
  const running = jobs.filter((j) =>
    ["queued", "running", "cancelling"].includes(j.status),
  );
  const chosenBag = bags.find((b) => b.id === bag),
    first = series.find((s) => !hidden.has(s.run_id));
  const current: Section =
    panel === "history"
      ? "experiments"
      : panel === "train" || panel === "tune"
        ? "training"
        : panel === "experiment"
          ? "experiments"
          : page;
  const titles: Record<Section, string> = {
    analysis: "Анализ",
    experiments: "Эксперименты",
    data: "Данные",
    models: "Модели",
    training: "Обучение и подбор",
  };
  const navigate = (section: Section) => {
    setError("");
    if (section === "experiments") open("history");
    else if (section === "training") open("train");
    else {
      setPanel(null);
      setPage(section);
    }
  };
  const useModel = (
    id: string,
    target: "experiment" | "train" | "tune",
    artifact?: string,
  ) => {
    open(target);
    setChosen([id]);
    setWeightIds((x) => ({ ...x, [id]: artifact || "" }));
  };
  return (
    <div className="app-shell">
      <Sidebar
        current={current}
        connected={connected}
        onChange={navigate}
        onNewExperiment={() => open("experiment")}
      />
      <div className="workspace">
        <header className="topbar">
          <h1>
            {panel === "experiment" ? "Новый эксперимент" : titles[current]}
          </h1>
          <div className="top-actions">
            {running.length > 0 && (
              <button className="quiet" onClick={() => open("history")}>
                <LoaderCircle size={13} className="spin" />В очереди:{" "}
                {running.length}
              </button>
            )}
            {current === "analysis" && <span className="grid-tag">REPLAY</span>}
            <button className="primary" onClick={() => open("experiment")}>
              <Plus size={14} />
              Новый эксперимент
            </button>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button onClick={() => setError("")} aria-label="Закрыть ошибку">
              <X size={16} />
            </button>
          </div>
        )}
        <div className="page-content">
          {!panel && page === "analysis" && (
            <main className="analysis-page">
              <div className="selection-bar">
                <div className="select-group">
                  <span className="field-icon">
                    <TrainFront size={18} />
                  </span>
                  <div>
                    <label>ПОЕЗДКА</label>
                    <select
                      aria-label="Поездка для просмотра"
                      value={bag}
                      onChange={(e) => setBag(e.target.value)}
                    >
                      {!availableBags.length && (
                        <option value="">Нет результатов</option>
                      )}
                      {availableBags.map((id) => (
                        <option key={id}>{id}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="selection-divider" />
                <div className="trip-meta">
                  <span>
                    Трамвай <b>{chosenBag?.vehicle || "—"}</b>
                  </span>
                  <span>
                    <Clock3 size={13} />
                    {chosenBag ? stamp(chosenBag.duration_s) : "—"}
                  </span>
                  <span>
                    <Radio size={13} />
                    {geometry?.source
                      ? "GNSS " + geometry.source
                      : "GNSS недоступен"}
                  </span>
                </div>
                <div className="selection-spacer" />
                <button className="quiet" onClick={() => open("history")}>
                  <GitBranch size={15} />
                  {selectedRuns.length}{" "}
                  {selectedRuns.length === 1 ? "модель" : "модели"}
                  <ChevronDown size={14} />
                </button>
                <span className="grid-tag">20 Гц</span>
              </div>
              <div className="metric-grid">
                <Metric
                  label="RMSE скор."
                  value={fmt(first?.metrics.speed.rmse_mps)}
                  unit="м/с"
                  icon={<Gauge size={17} />}
                  note="Среднеквадратичная ошибка"
                />
                <Metric
                  label="RMSE пути"
                  value={fmt(first?.metrics.path.rmse_m, 2)}
                  unit="м"
                  icon={<GitBranch size={17} />}
                  note="На непрерывных участках"
                />
                <Metric
                  label="Покрытие GNSS"
                  value={first ? fmt(first.metrics.coverage * 100, 1) : "—"}
                  unit="%"
                  icon={<Radio size={17} />}
                  note="Совместно доступные отсчёты"
                />
                <Metric
                  label="Доступность"
                  value={
                    first
                      ? fmt(first.metrics.prediction_coverage * 100, 1)
                      : "—"
                  }
                  unit="%"
                  icon={<Activity size={17} />}
                  note={
                    first
                      ? `${first.total_points.toLocaleString("ru-RU")} тактов расчёта`
                      : "Ожидание результатов"
                  }
                />
              </div>
              <div className="monitor-heading">
                <h2>
                  <span className="connection-dot" />
                  Воспроизведение поездки
                </h2>
                <div className="legend">
                  <span>
                    <i style={{ background: "#273f54" }} />
                    GNSS — факт
                  </span>
                  {series.map((s, i) => (
                    <button
                      key={s.run_id}
                      className={hidden.has(s.run_id) ? "muted" : ""}
                      onClick={() =>
                        setHidden((old) => {
                          const next = new Set(old);
                          if (next.has(s.run_id)) next.delete(s.run_id);
                          else next.add(s.run_id);
                          return next;
                        })
                      }
                    >
                      <i style={{ background: colors[i % colors.length] }} />
                      {s.run_id.split("/").pop()}
                    </button>
                  ))}
                </div>
              </div>
              <div className="monitor">
                <MapPanel
                  geometry={geometry}
                  series={series}
                  cursor={cursor}
                  hidden={hidden}
                />
                <div className="chart-workspace">
                  <div
                    className="chart-tabs"
                    role="tablist"
                    aria-label="Показатели"
                  >
                    {(
                      [
                        ["all", "Все показатели"],
                        ["speed", "Скорость"],
                        ["path", "Путь"],
                        ["diag", "Диагностика"],
                      ] as const
                    ).map(([id, label]) => (
                      <button
                        key={id}
                        role="tab"
                        aria-selected={chartMode === id}
                        className={chartMode === id ? "active" : ""}
                        onClick={() => setChartMode(id)}
                      >
                        {label}
                      </button>
                    ))}
                    <span className="chart-truth">– – Эталон GNSS</span>
                  </div>
                  {chartMode === "diag" && (
                    <label className="diagnostic-picker">
                      Сигнал{" "}
                      <select
                        value={diagnostic}
                        onChange={(e) => setDiagnostic(e.target.value)}
                      >
                        <option value="">Выберите сигнал</option>
                        {diagnosticNames.map((d) => (
                          <option key={d}>{d}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  <Charts
                    mode={chartMode}
                    series={series}
                    cursor={cursor}
                    onCursor={(t) => {
                      setPlaying(false);
                      setCursor(t);
                    }}
                    hidden={hidden}
                    diagnostic={diagnostic}
                    zoom={zoom}
                    onZoom={setZoom}
                  />
                </div>
                {loading && (
                  <div className="loading-layer">
                    <LoaderCircle className="spin" size={26} />
                    <span>Подготовка поездки…</span>
                  </div>
                )}
              </div>
              <div className="playback">
                <button
                  className="icon-button"
                  title="В начало"
                  onClick={() => {
                    setCursor(start);
                    setPlaying(false);
                  }}
                >
                  <SkipBack size={17} />
                </button>
                <button
                  className="play-button"
                  aria-label={playing ? "Пауза" : "Воспроизвести"}
                  onClick={() => {
                    if (cursor >= end) setCursor(start);
                    setPlaying(!playing);
                  }}
                  disabled={!series.length}
                >
                  {playing ? <Pause size={18} /> : <Play size={18} />}
                </button>
                <span className="timecode">
                  {stamp(cursor - start)}
                  <span> / {stamp(end - start)}</span>
                </span>
                <input
                  aria-label="Время воспроизведения"
                  className="timeline"
                  type="range"
                  min={start}
                  max={end || 1}
                  step="0.05"
                  value={cursor}
                  onChange={(e) => {
                    setPlaying(false);
                    setCursor(+e.target.value);
                  }}
                />
                <select
                  aria-label="Скорость воспроизведения"
                  className="speed-select"
                  value={speed}
                  onChange={(e) => setSpeed(+e.target.value)}
                >
                  {[0.5, 1, 2, 5, 10, 20, 50].map((s) => (
                    <option key={s} value={s}>
                      {s}×
                    </option>
                  ))}
                </select>
                <button
                  className="quiet"
                  onClick={() => setZoom([0, 100])}
                  title="Сбросить масштаб графиков"
                >
                  <RefreshCw size={15} />
                </button>
              </div>
              <div className="results-heading">
                <h2>Сравнение моделей</h2>
                <button
                  className="quiet"
                  onClick={() => setExtraMetrics(!extraMetrics)}
                >
                  {extraMetrics
                    ? "Скрыть доп. метрики"
                    : "Показать доп. метрики"}
                </button>
                <span className="help">
                  Вся поездка · ошибка = прогноз − эталон
                </span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Модель / запуск</th>
                      <th>RMSE, м/с</th>
                      <th>MAE, м/с</th>
                      {extraMetrics && <th>Bias, м/с</th>}
                      {extraMetrics && <th>P95, м/с</th>}
                      <th>RMSE пути, м</th>
                      <th>Покрытие</th>
                      {extraMetrics && <th>Расчёт, с</th>}
                      {extraMetrics && <th>Память, MiB</th>}
                      <th>Артефакты</th>
                    </tr>
                  </thead>
                  <tbody>
                    {series.map((s, i) => (
                      <tr key={s.run_id}>
                        <td>
                          <i
                            className="table-dot"
                            style={{ background: colors[i % colors.length] }}
                          />
                          {s.run_id.split("/").pop()}
                        </td>
                        <td className="emphasis">
                          {fmt(s.metrics.speed.rmse_mps)}
                        </td>
                        <td>{fmt(s.metrics.speed.mae_mps)}</td>
                        {extraMetrics && (
                          <td>{fmt(s.metrics.speed.bias_mps)}</td>
                        )}
                        {extraMetrics && (
                          <td>{fmt(s.metrics.speed.p95_abs_mps)}</td>
                        )}
                        <td>{fmt(s.metrics.path.rmse_m, 2)}</td>
                        <td>{fmt(s.metrics.coverage * 100, 1)}%</td>
                        {extraMetrics && (
                          <td>{fmt(s.resources?.wall_seconds, 2)}</td>
                        )}
                        {extraMetrics && (
                          <td>
                            {fmt(
                              s.resources?.peak_process_rss_bytes_sampled
                                ? s.resources.peak_process_rss_bytes_sampled /
                                    1048576
                                : null,
                              1,
                            )}
                          </td>
                        )}
                        <td className="downloads">
                          <a
                            href={`/api/v1/download?run=${encodeURIComponent(s.run_id)}&file=${encodeURIComponent("bags/" + bag + "/predictions.csv")}`}
                          >
                            <ArrowDownToLine size={13} />
                            CSV
                          </a>
                          <a
                            href={`/api/v1/download?run=${encodeURIComponent(s.run_id)}&file=metrics.json`}
                          >
                            JSON
                          </a>
                          <a
                            href={`/api/v1/download?run=${encodeURIComponent(s.run_id)}&file=config.yaml`}
                          >
                            YAML
                          </a>
                          <a
                            href={`/api/v1/download?run=${encodeURIComponent(s.run_id)}&file=resources.json`}
                          >
                            Ресурсы
                          </a>
                        </td>
                      </tr>
                    ))}
                    {!series.length && (
                      <tr>
                        <td colSpan={10} className="empty-table">
                          Выберите сохранённый запуск в разделе «Эксперименты»
                          или создайте новый эксперимент.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </main>
          )}
          {!panel && page === "data" && (
            <DataPage
              bags={bags}
              onUse={(ids) => {
                open("experiment");
                setChosenBags(ids);
                setSelectionMode("bags");
              }}
            />
          )}
          {!panel && page === "models" && (
            <ModelsPage
              models={models}
              artifacts={artifacts}
              onUse={useModel}
            />
          )}
          {panel === "history" && (
            <ExperimentsPage
              jobs={jobs}
              runs={runs}
              selected={selectedRuns}
              onToggle={compare}
              expanded={expandedJob}
              onExpand={setExpandedJob}
              onRetry={replayJob}
              onCancel={async (job) => {
                try {
                  await post("/jobs/" + job.id + "/cancel", {});
                  await refresh();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
              onShow={(ids) => {
                if (ids) setSelectedRuns(ids);
                setPanel(null);
                setPage("analysis");
              }}
            />
          )}
          {panel && panel !== "history" && (
            <div className="config-layout">
              <div className="config-main">
                <div className="drawer-content">
                  <div className="form-tabs">
                    <button
                      className={panel === "experiment" ? "active" : ""}
                      onClick={() => open("experiment")}
                    >
                      Эксперимент
                    </button>
                    <button
                      className={panel === "train" ? "active" : ""}
                      onClick={() => open("train")}
                    >
                      Обучение
                    </button>
                    <button
                      className={panel === "tune" ? "active" : ""}
                      onClick={() => open("tune")}
                    >
                      Подбор
                    </button>
                  </div>
                  <label className="form-field">
                    Название
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Например: устойчивость к потере переднего датчика"
                    />
                  </label>
                  <h3 className="section-title">
                    01 <span>Данные</span>
                  </h3>
                  {panel === "experiment" && (
                    <div className="segmented">
                      <button
                        className={selectionMode === "bags" ? "active" : ""}
                        onClick={() => setSelectionMode("bags")}
                      >
                        Поездки
                      </button>
                      <button
                        className={selectionMode === "split" ? "active" : ""}
                        onClick={() => setSelectionMode("split")}
                      >
                        Выборка
                      </button>
                    </div>
                  )}
                  {panel === "experiment" && selectionMode === "bags" ? (
                    <TripPicker
                      bags={bags}
                      value={chosenBags}
                      onChange={setChosenBags}
                    />
                  ) : (
                    <>
                      <div className="form-grid">
                        <label className="form-field">
                          Разбиение
                          <select
                            value={split}
                            onChange={(e) => setSplit(e.target.value)}
                          >
                            <option value="chronological">
                              Хронологическое · 70 / 15 / 15
                            </option>
                            <option value="cross_vehicle">
                              Перенос между трамваями
                            </option>
                          </select>
                        </label>
                        {split === "cross_vehicle" && (
                          <label className="form-field">
                            Обучающий трамвай
                            <select
                              value={vehicle}
                              onChange={(e) => setVehicle(e.target.value)}
                            >
                              <option>30618</option>
                              <option>30639</option>
                            </select>
                          </label>
                        )}
                        {panel === "experiment" && (
                          <label className="form-field">
                            Выборка
                            <select
                              value={subset}
                              onChange={(e) => setSubset(e.target.value)}
                            >
                              <option value="train">Train</option>
                              <option value="validation">Validation</option>
                              <option value="test">
                                Test · отдельная оценка
                              </option>
                            </select>
                          </label>
                        )}
                      </div>
                      {panel !== "experiment" && (
                        <div className="info-box">
                          {panel === "train"
                            ? "Обучение использует только свежие согласованные колёса train-поездок. Проверка выполняется на validation."
                            : "Кандидаты сравниваются на validation по RMSE скорости с контролем покрытия."}{" "}
                          Test не используется.
                        </div>
                      )}
                    </>
                  )}
                  {panel !== "experiment" && (
                    <SplitPicker
                      strategy={split}
                      vehicle={vehicle}
                      bags={bags}
                      value={trainingSelection}
                      onChange={setTrainingSelection}
                    />
                  )}
                  <h3 className="section-title">
                    02 <span>Модели</span>
                  </h3>
                  <div className="model-grid">
                    {models
                      .filter((m) => panel !== "train" || m.training)
                      .map((m) => (
                        <button
                          type="button"
                          key={m.id}
                          className={
                            "model-option " +
                            (chosen.includes(m.id) ? "active" : "")
                          }
                          onClick={() => toggleModel(m.id)}
                        >
                          <span className="model-check">
                            {chosen.includes(m.id) && <Check size={12} />}
                          </span>
                          <span>
                            {m.label}
                            <small>
                              {m.aliases.length
                                ? "odometry_lab + hack · проверенный алиас"
                                : m.id.startsWith("hack")
                                  ? "Замороженное ядро hack"
                                  : "odometry_lab"}
                            </small>
                          </span>
                        </button>
                      ))}
                  </div>
                  {chosen.map((id) => {
                    const model = models.find((m) => m.id === id);
                    return (
                      <details className="model-settings" key={id}>
                        <summary>
                          <Settings2 size={14} />
                          {model?.label || id}
                          <span>Параметры и веса</span>
                        </summary>
                        <label className="form-field">
                          Версия модели
                          <select
                            value={weightIds[id] || ""}
                            onChange={(e) =>
                              setWeightIds((x) => ({
                                ...x,
                                [id]: e.target.value,
                              }))
                            }
                          >
                            <option value="">Исходная конфигурация</option>
                            {artifacts
                              .filter((a) => a.model_id === id)
                              .map((a) => (
                                <option value={a.id} key={a.id}>
                                  {a.name}
                                </option>
                              ))}
                          </select>
                        </label>
                        <label className="form-field">
                          Переопределение параметров · JSON
                          <textarea
                            className="code-input"
                            rows={5}
                            value={params[id] || "{}"}
                            onChange={(e) =>
                              setParams((x) => ({ ...x, [id]: e.target.value }))
                            }
                          />
                        </label>
                        <details className="defaults">
                          <summary>Параметры по умолчанию и единицы</summary>
                          <pre>{JSON.stringify(model?.defaults, null, 2)}</pre>
                          <div className="parameter-list">
                            {model?.parameters.map((p) => (
                              <span key={p.name}>
                                {p.name} {p.unit && `(${p.unit})`}
                              </span>
                            ))}
                          </div>
                        </details>
                      </details>
                    );
                  })}
                  {panel === "tune" && (
                    <>
                      <h3 className="section-title">
                        03 <span>Поиск параметров</span>
                      </h3>
                      <div className="form-grid">
                        <label className="form-field">
                          Бюджет кандидатов
                          <input
                            type="number"
                            min="2"
                            max="200"
                            value={budget}
                            onChange={(e) => setBudget(+e.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          Минимум покрытия от исходного, %
                          <input
                            type="number"
                            min="1"
                            max="100"
                            value={coverage}
                            onChange={(e) => setCoverage(+e.target.value)}
                          />
                        </label>
                      </div>
                      <label className="form-field">
                        Диапазоны или списки значений · JSON
                        <textarea
                          className="code-input"
                          rows={7}
                          value={ranges}
                          onChange={(e) => setRanges(e.target.value)}
                        />
                      </label>
                      <p className="help">
                        Числа: {`{"min": 0.1, "max": 1}`}. Дискретные значения:{" "}
                        {`{"values": [true, false]}`}. Вложенные параметры:
                        core.max_age_s. Первый кандидат — исходная конфигурация.
                      </p>
                    </>
                  )}
                  <h3 className="section-title">
                    {panel === "tune" ? "04" : "03"}{" "}
                    <span>
                      {panel === "train"
                        ? "Сценарий проверки"
                        : "Отказы датчиков"}
                    </span>
                    <button
                      className="quiet"
                      onClick={() =>
                        setFaults((x) => [
                          ...x,
                          {
                            kind: "drop",
                            topic: "both",
                            start_s: 10,
                            end_s: 20,
                            value: 1.1,
                            probability: 1,
                          },
                        ])
                      }
                    >
                      <Plus size={14} />
                      Добавить
                    </button>
                  </h3>
                  {!faults.length && (
                    <div className="empty-fault">
                      Чистый сигнал · искажения не добавлены
                    </div>
                  )}
                  {faults.map((f, i) => (
                    <div className="fault-card" key={i}>
                      <div className="fault-heading">
                        <b>Отказ {i + 1}</b>
                        <button
                          className="icon-button"
                          onClick={() =>
                            setFaults((x) => x.filter((_, j) => j !== i))
                          }
                        >
                          <X size={15} />
                        </button>
                      </div>
                      <div className="form-grid">
                        <label className="form-field">
                          Тип
                          <select
                            value={f.kind}
                            onChange={(e) =>
                              setFaults((x) =>
                                x.map((v, j) =>
                                  j === i
                                    ? {
                                        ...v,
                                        kind: e.target.value,
                                        value:
                                          e.target.value === "delay"
                                            ? 0.2
                                            : e.target.value === "spike"
                                              ? 10
                                              : 1.1,
                                      }
                                    : v,
                                ),
                              )
                            }
                          >
                            {["drop", "delay", "spike", "freeze", "scale"].map(
                              (k) => (
                                <option key={k}>{k}</option>
                              ),
                            )}
                          </select>
                        </label>
                        <label className="form-field">
                          Вход
                          <select
                            value={f.topic}
                            onChange={(e) =>
                              setFaults((x) =>
                                x.map((v, j) =>
                                  j === i ? { ...v, topic: e.target.value } : v,
                                ),
                              )
                            }
                          >
                            {Object.entries(topicNames).map(([key, label]) => (
                              <option value={key} key={key}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </label>
                        {(
                          [
                            "start_s",
                            "end_s",
                            "probability",
                            ...(["spike", "delay", "scale"].includes(f.kind)
                              ? ["value"]
                              : []),
                          ] as (keyof Fault)[]
                        ).map((key) => (
                          <label className="form-field" key={key}>
                            {
                              {
                                start_s: "Начало, с",
                                end_s: "Конец, с",
                                probability: "Вероятность",
                                value:
                                  f.kind === "delay"
                                    ? "Задержка, с"
                                    : f.kind === "scale"
                                      ? "Множитель"
                                      : "Амплитуда · сырые единицы",
                              }[key as string]
                            }
                            <input
                              type="number"
                              step="any"
                              value={f[key]}
                              onChange={(e) =>
                                setFaults((x) =>
                                  x.map((v, j) =>
                                    j === i
                                      ? { ...v, [key]: +e.target.value }
                                      : v,
                                  ),
                                )
                              }
                            />
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                  <div className="form-grid">
                    <label className="form-field">
                      Seed
                      <input
                        type="number"
                        value={seed}
                        onChange={(e) => setSeed(+e.target.value)}
                      />
                    </label>
                    <label className="form-field">
                      Сетка расчёта
                      <input value="50 мс · 20 Гц" disabled />
                    </label>
                  </div>
                  <details className="model-settings">
                    <summary>
                      <Settings2 size={14} />
                      Дополнительная маска качества
                    </summary>
                    <p className="help">
                      Исходные метрики сохраняются всегда. Например:{" "}
                      {`{"max_receiver_disagreement_mps": 0.5}`}
                    </p>
                    <textarea
                      className="code-input"
                      rows={4}
                      value={quality}
                      onChange={(e) => setQuality(e.target.value)}
                    />
                  </details>
                </div>
              </div>
              <aside className="config-summary">
                <h2>Конфигурация запуска</h2>
                <dl>
                  <dt>Тип</dt>
                  <dd>
                    {panel === "train"
                      ? "Обучение"
                      : panel === "tune"
                        ? "Подбор параметров"
                        : "Эксперимент"}
                  </dd>
                  <dt>Модели</dt>
                  <dd>{chosen.join(", ") || "Не выбраны"}</dd>
                  <dt>Данные</dt>
                  <dd>
                    {panel === "experiment" && selectionMode === "bags"
                      ? `${chosenBags.length} поездок`
                      : split === "chronological"
                        ? "Хронологическое 70/15/15"
                        : "Cross-vehicle"}
                  </dd>
                  <dt>Seed</dt>
                  <dd>{seed}</dd>
                  <dt>Сценарии отказов</dt>
                  <dd>{faults.length}</dd>
                  {panel === "tune" && (
                    <>
                      <dt>Кандидаты</dt>
                      <dd>{budget}</dd>
                      <dt>Порог покрытия</dt>
                      <dd>{coverage}% от исходного</dd>
                    </>
                  )}
                </dl>
                <p className="help">
                  {panel === "experiment"
                    ? "Прогнозы и метрики сохраняются для каждой модели. Запуски можно сравнить в разделе «Анализ»."
                    : "Обучение использует train, подбор — validation. Test оценивается отдельным запуском."}
                </p>
                <footer className="drawer-footer">
                  <span>
                    <span className="connection-dot" />
                    Результаты сохраняются автоматически
                  </span>
                  <button className="primary" disabled={busy} onClick={submit}>
                    {busy ? (
                      <LoaderCircle size={16} className="spin" />
                    ) : (
                      <Play size={15} />
                    )}{" "}
                    {panel === "train"
                      ? "Обучить модель"
                      : panel === "tune"
                        ? "Запустить подбор"
                        : "Запустить эксперимент"}
                  </button>
                </footer>
              </aside>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
function Metric({
  label,
  value,
  unit,
  note,
}: {
  label: string;
  value: string;
  unit: string;
  icon: React.ReactNode;
  note: string;
}) {
  return (
    <div className="metric" title={note}>
      <span>{label}</span>
      <strong className="font-mono">{value}</strong>
      <small>{unit}</small>
    </div>
  );
}
