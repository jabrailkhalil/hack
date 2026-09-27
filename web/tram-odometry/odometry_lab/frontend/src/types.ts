export type Model = {
  id: string;
  label: string;
  defaults: Record<string, unknown>;
  training: boolean;
  aliases: string[];
  parameters: {
    name: string;
    default: number | boolean;
    type: string;
    unit: string;
  }[];
};
export type Bag = {
  id: string;
  vehicle: string;
  duration_s: number;
  has_gnss: boolean;
};
export type Metrics = {
  speed: {
    rmse_mps: number | null;
    mae_mps: number | null;
    bias_mps: number | null;
    p95_abs_mps: number | null;
  };
  path: { rmse_m: number | null; covered_end_error_sum_m: number | null };
  coverage: number;
  prediction_coverage: number;
};
export type Run = {
  id: string;
  config: { estimator: Record<string, unknown>; bags: string[] };
  metrics: {
    aggregate: { pooled_speed: Metrics["speed"]; coverage: number };
    bags: { id: string; metrics: Metrics }[];
  };
  updated: number;
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  created: string;
  request: Record<string, any>;
  result: { runs?: string[]; artifact?: string } | null;
  error: string | null;
  log: string;
};
export type Artifact = {
  id: string;
  name: string;
  model_id: string;
  kind: string;
  created: string;
  validation: any;
};
export type Series = {
  plot_distance: (number | null)[];
  resources?: {
    wall_seconds?: number;
    peak_process_rss_bytes_sampled?: number;
  };
  run_id: string;
  bag: string;
  total_points: number;
  t: number[];
  time_ns: string[];
  velocity: (number | null)[];
  reference: (number | null)[];
  error: (number | null)[];
  distance: (number | null)[];
  reference_distance: (number | null)[];
  local_distance: (number | null)[];
  distance_error: (number | null)[];
  path_segment: number[];
  geo_segment: number[];
  predicted_position: ([number, number] | [null, null])[];
  actual_position: ([number, number] | [null, null])[];
  diagnostics: Record<string, (number | null)[]>;
  status: string[];
  metrics: Metrics;
};
export type Geometry = {
  source: string | null;
  segments: {
    t: number[];
    lat: number[];
    lon: number[];
    arc: number[];
    route: [number, number][];
    route_arc: number[];
  }[];
};
export const colors = [
  "#92400e",
  "#b45309",
  "#78716c",
  "#c2410c",
  "#a16207",
  "#44403c",
  "#7c2d12",
  "#d97706",
];
export const fmt = (n: number | null | undefined, d = 3) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : n.toLocaleString("ru-RU", {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      });
export function nearest(t: number[], value: number) {
  let a = 0,
    b = t.length - 1;
  while (a < b) {
    const m = (a + b) >> 1;
    if (t[m] < value) a = m + 1;
    else b = m;
  }
  return a > 0 && value - t[a - 1] < t[a] - value ? a - 1 : a;
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api/v1" + path, init);
  if (!response.ok) {
    const err = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail),
    );
  }
  return response.json();
}
export const post = <T>(path: string, body: unknown) =>
  api<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
