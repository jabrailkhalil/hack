import { useState } from "react";
import { Bag } from "./types";

export default function TripPicker({
  bags,
  value,
  onChange,
}: {
  bags: Bag[];
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const [search, setSearch] = useState(""),
    [vehicle, setVehicle] = useState("");
  const filtered = bags.filter(
    (b) =>
      b.id.toLowerCase().includes(search.toLowerCase()) &&
      (!vehicle || b.vehicle === vehicle),
  );
  return (
    <div className="trip-picker">
      <div className="toolbar">
        <input
          aria-label="Найти поездку для эксперимента"
          placeholder="Поиск по ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Трамвай для эксперимента"
          value={vehicle}
          onChange={(e) => setVehicle(e.target.value)}
        >
          <option value="">Все трамваи</option>
          {[...new Set(bags.map((b) => b.vehicle))].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
        <button
          type="button"
          className="quiet"
          onClick={() => onChange([])}
          disabled={!value.length}
        >
          Сбросить ({value.length})
        </button>
      </div>
      <div className="trip-picker-table">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Поездка</th>
              <th>Трамвай</th>
              <th>Длительность</th>
              <th>GNSS</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((b) => (
              <tr key={b.id}>
                <td>
                  <input
                    aria-label={`Поездка ${b.id}`}
                    type="checkbox"
                    checked={value.includes(b.id)}
                    onChange={(e) =>
                      onChange(
                        e.target.checked
                          ? [...value, b.id]
                          : value.filter((id) => id !== b.id),
                      )
                    }
                  />
                </td>
                <td className="font-mono">{b.id}</td>
                <td>{b.vehicle}</td>
                <td className="font-mono">
                  {Math.floor(b.duration_s / 60)}:
                  {String(Math.floor(b.duration_s % 60)).padStart(2, "0")}
                </td>
                <td>{b.has_gnss ? "Да" : "Нет"}</td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={5} className="empty-state">
                  Поездки не найдены
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
