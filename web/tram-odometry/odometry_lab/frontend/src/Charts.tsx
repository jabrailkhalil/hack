import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  GraphicComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  GraphicComponent,
  CanvasRenderer,
]);
import { colors, fmt, nearest, Series } from "./types";
import { useTheme } from "./ThemeContext";
type Props = {
  mode: "all" | "speed" | "path" | "diag";
  series: Series[];
  cursor: number;
  onCursor: (t: number) => void;
  hidden: Set<string>;
  diagnostic: string;
  zoom: [number, number];
  onZoom: (v: [number, number]) => void;
};

function Chart({
  title,
  unit,
  field,
  reference,
  error,
  series,
  cursor,
  onCursor,
  hidden,
  zoom,
  onZoom,
}: {
  title: string;
  unit: string;
  field: string;
  reference?: string;
  error?: boolean;
} & Omit<Props, "diagnostic">) {
  const { theme } = useTheme();
  const palette =
    theme === "dark"
      ? {
          grid: "#292524",
          tick: "#a8a29e",
          text: "#f5f5f4",
          surface: "#1c1917",
          border: "#44403c",
          accent: "#eed7b7",
        }
      : {
          grid: "#e7e5e4",
          tick: "#78716c",
          text: "#292524",
          surface: "#fafaf9",
          border: "#d6d3d1",
          accent: "#6f4d3b",
        };
  const node = useRef<HTMLDivElement>(null),
    instance = useRef<echarts.ECharts | null>(null),
    onTime = useRef(onCursor),
    onRange = useRef(onZoom);
  onTime.current = onCursor;
  onRange.current = onZoom;
  useEffect(() => {
    if (!node.current) return;
    const chart = echarts.init(node.current);
    instance.current = chart;
    chart.getZr().on("mousemove", (event: any) => {
      if (
        chart.containPixel({ gridIndex: 0 }, [event.offsetX, event.offsetY])
      ) {
        const value = chart.convertFromPixel({ xAxisIndex: 0 }, event.offsetX);
        if (typeof value === "number") onTime.current(value);
      }
    });
    chart.on("datazoom", (event: any) => {
      const v = event.batch?.[0] || event;
      if (v.start != null && v.end != null) onRange.current([v.start, v.end]);
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(node.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, []);
  const active = series.filter((s) => !hidden.has(s.run_id));
  const lines = useMemo(() => {
    const output: any[] = [];
    const points = (s: Series, key: string) => {
      const values = (s as any)[key] ?? s.diagnostics[key] ?? [];
      const data: any[] = [];
      s.t.forEach((t, i) => {
        if (
          i > 0 &&
          (key.includes("distance") || field.includes("distance")) &&
          s.path_segment[i] !== s.path_segment[i - 1]
        )
          data.push([t, null]);
        data.push([t, values[i]]);
      });
      return data;
    };
    if (reference) {
      series.forEach((s, i) => {
        if (hidden.has(s.run_id)) return;
        if (
          reference === "reference" &&
          output.some((s) => s.name === "Эталон GNSS")
        )
          return;
        output.push({
          name:
            reference === "reference"
              ? "Эталон GNSS"
              : `Эталон · ${s.run_id.split("/").pop()}`,
          type: "line",
          showSymbol: false,
          connectNulls: false,
          data: points(s, reference),
          lineStyle: { color: "#94a3b8", width: 1.4, type: "dashed" },
          itemStyle: { color: "#94a3b8" },
          silent: false,
        });
      });
    }
    series.forEach((s, i) => {
      if (hidden.has(s.run_id)) return;
      output.push({
        name: s.run_id.split("/").pop(),
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: points(s, field),
        lineStyle: { color: colors[i % colors.length], width: 1.7 },
        itemStyle: { color: colors[i % colors.length] },
        markLine: error
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: "#59616d", width: 1 },
              label: { show: false },
              data: [{ yAxis: 0 }],
            }
          : undefined,
      });
    });
    return output;
  }, [series, hidden, field, reference, error]);
  useEffect(() => {
    instance.current?.setOption(
      {
        animation: false,
        backgroundColor: "transparent",
        textStyle: { fontFamily: "Inter, system-ui" },
        grid: { left: 48, right: 16, top: 5, bottom: 20 },
        tooltip: {
          trigger: "axis",
          backgroundColor: palette.surface,
          borderColor: palette.border,
          textStyle: { color: palette.text, fontSize: 11 },
          valueFormatter: (v: unknown) =>
            typeof v === "number" ? fmt(v) : "—",
        },
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        xAxis: {
          type: "value",
          min: series[0]?.t[0] ?? 0,
          max: series[0]?.t.at(-1) ?? 100,
          axisLabel: {
            color: palette.tick,
            fontSize: 10,
            formatter: (v: number) => `${Math.round(v)} с`,
          },
          axisLine: { lineStyle: { color: palette.border } },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: { color: palette.tick, fontSize: 10 },
          splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
          axisPointer: { show: false },
        },
        dataZoom: [
          { type: "inside", start: zoom[0], end: zoom[1], filterMode: "none" },
        ],
        series: lines,
      },
      true,
    );
  }, [lines, series, theme]);
  useEffect(() => {
    const chart = instance.current;
    if (!chart) return;
    chart.dispatchAction(
      { type: "dataZoom", start: zoom[0], end: zoom[1] },
      { silent: true },
    );
  }, [zoom]);
  useEffect(() => {
    const chart = instance.current;
    if (!chart) return;
    const x = chart.convertToPixel({ xAxisIndex: 0 }, cursor);
    chart.setOption({
      graphic: [
        {
          id: "cursor",
          type: "line",
          silent: true,
          shape: { x1: x, y1: 5, x2: x, y2: chart.getHeight() - 20 },
          style: { stroke: palette.accent, lineWidth: 1, opacity: 0.7 },
          invisible: !Number.isFinite(x) || x < 48 || x > chart.getWidth() - 20,
        },
      ],
    });
  }, [cursor, zoom, lines, theme]);
  const first = active[0];
  const values = first
    ? ((first as any)[field] ?? first.diagnostics[field])
    : [];
  const v = first ? values?.[nearest(first.t, cursor)] : null;
  return (
    <section className="chart-card">
      <header>
        <span className={error ? "chart-dot error" : "chart-dot"} />
        <h3>{title}</h3>
        <span className="chart-unit">{unit}</span>
        <strong>{fmt(v, 2)}</strong>
      </header>
      <div className="chart-canvas" ref={node} />
    </section>
  );
}
export default function Charts(props: Props) {
  return (
    <div className={"charts mode-" + props.mode}>
      {(props.mode === "all" || props.mode === "speed") && (
        <>
          <Chart
            {...props}
            title="Скорость"
            unit="м/с"
            field="velocity"
            reference="reference"
          />
          <Chart
            {...props}
            title="Ошибка скорости"
            unit="м/с"
            field="error"
            error
          />
        </>
      )}
      {(props.mode === "all" || props.mode === "path") && (
        <>
          <Chart
            {...props}
            title="Пройденный путь"
            unit="м · по участкам"
            field="plot_distance"
            reference="reference_distance"
          />
          <Chart
            {...props}
            title="Ошибка пути"
            unit="м"
            field="distance_error"
            error
          />
        </>
      )}
      {props.mode === "diag" && props.diagnostic && (
        <Chart
          {...props}
          title={props.diagnostic}
          unit="диагностика"
          field={props.diagnostic}
        />
      )}
      {props.mode === "diag" && !props.diagnostic && (
        <div className="empty-state">
          Выберите числовой выход модели для просмотра.
        </div>
      )}
    </div>
  );
}
