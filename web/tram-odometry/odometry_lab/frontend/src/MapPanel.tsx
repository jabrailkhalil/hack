import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Crosshair, MapPinned, Route } from "lucide-react";
import { api, colors, Geometry, nearest, Series } from "./types";
import { smoothRoute } from "./geometry";

export default function MapPanel({
  geometry,
  series,
  cursor,
  hidden,
}: {
  geometry: Geometry | null;
  series: Series[];
  cursor: number;
  hidden: Set<string>;
}) {
  const node = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    route = useRef<L.LayerGroup | null>(null),
    markers = useRef<L.LayerGroup | null>(null);
  const [smooth, setSmooth] = useState(true),
    [tileError, setTileError] = useState(false),
    [follow, setFollow] = useState(false);
  useEffect(() => {
    if (!node.current) return;
    const m = L.map(node.current, {
      zoomControl: false,
      preferCanvas: true,
    }).setView([55.75, 37.61], 11);
    map.current = m;
    L.control.zoom({ position: "bottomright" }).addTo(m);
    const tiles = L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        attribution:
          '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      },
    );
    tiles.on("tileerror", () => setTileError(true));
    tiles.addTo(m);
    api<{ tile_url: string }>("/display")
      .then((config) => {
        if (
          config.tile_url !==
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png" &&
          map.current === m
        )
          tiles.setUrl(config.tile_url);
      })
      .catch(() => {});
    route.current = L.layerGroup().addTo(m);
    markers.current = L.layerGroup().addTo(m);
    const observer = new ResizeObserver(() => m.invalidateSize());
    observer.observe(node.current);
    return () => {
      observer.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    route.current?.clearLayers();
    if (!geometry) return;
    const bounds = L.latLngBounds([]);
    for (const seg of geometry.segments) {
      if (seg.route.length < 2) continue;
      const points = smooth ? smoothRoute(seg.route) : seg.route;
      L.polyline(points, { color: "#ffffff", weight: 8, opacity: 0.95 }).addTo(
        route.current!,
      );
      L.polyline(points, { color: "#243b4b", weight: 4, opacity: 0.85 }).addTo(
        route.current!,
      );
      L.polyline(points, {
        color: "#b7c8d3",
        weight: 1,
        dashArray: "2 7",
      }).addTo(route.current!);
      seg.route.forEach((p) => bounds.extend(p));
    }
    if (bounds.isValid())
      map.current?.fitBounds(bounds, { padding: [45, 45], maxZoom: 16 });
  }, [geometry, smooth]);
  useEffect(() => {
    markers.current?.clearLayers();
    if (!map.current || !markers.current) return;
    let actual: [number, number] | null = null;
    for (const segment of geometry?.segments || []) {
      if (
        cursor < segment.t[0] - 0.25 ||
        cursor > segment.t[segment.t.length - 1] + 0.25
      )
        continue;
      const ix = nearest(segment.t, cursor);
      if (Math.abs(segment.t[ix] - cursor) <= 0.25) {
        actual = [segment.lat[ix], segment.lon[ix]];
        break;
      }
    }
    series.forEach((s, i) => {
      if (!s.t.length) return;
      const ix = nearest(s.t, cursor);
      if (hidden.has(s.run_id)) return;
      const p = s.predicted_position[ix];
      if (p?.[0] != null) {
        L.circleMarker(p as [number, number], {
          radius: 10,
          color: "white",
          weight: 3,
          fillColor: colors[i % colors.length],
          fillOpacity: 1,
        })
          .bindTooltip(`Прогноз ${s.run_id.split("/").pop()}`, {
            direction: "top",
          })
          .addTo(markers.current!);
      }
    });
    if (actual) {
      L.marker(actual, {
        icon: L.divIcon({
          className: "truth-marker",
          html: "<span>Т</span>",
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        }),
      })
        .bindTooltip("Фактическое положение · GNSS", { direction: "top" })
        .addTo(markers.current);
      if (follow) map.current.panTo(actual, { animate: false });
    }
  }, [geometry, series, cursor, hidden, follow]);
  return (
    <section className="map-panel">
      <div ref={node} className="map-canvas" />
      <div className="map-caption">
        <MapPinned size={15} />
        <span>МАРШРУТ ПОЕЗДКИ</span>
        <span className="map-caption-source">
          GNSS · {geometry?.source || "нет координат"}
        </span>
      </div>
      <div className="map-controls">
        <button
          className={smooth ? "active" : ""}
          onClick={() => setSmooth(!smooth)}
        >
          <Route size={15} />
          Сглаживание
        </button>
        <button
          className={follow ? "active" : ""}
          onClick={() => setFollow(!follow)}
          title="Следовать за трамваем"
        >
          <Crosshair size={16} />
        </button>
      </div>
      {(!geometry || !geometry.segments.length) && (
        <div className="map-empty">
          {series.length
            ? "В этой поездке нет доступного GNSS-маршрута"
            : "Выберите результат или запустите эксперимент"}
        </div>
      )}
      <div className="map-note">
        {tileError
          ? "Подложка недоступна. Маршрут и расчёты доступны."
          : "Приближённая геометрия по GNSS · только для визуализации"}
      </div>
    </section>
  );
}
