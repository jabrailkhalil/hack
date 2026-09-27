import { useEffect, useState } from "react";
import { api, Bag } from "./types";
export default function SplitPicker({
  strategy,
  vehicle,
  bags,
  value,
  onChange,
}: {
  strategy: string;
  vehicle: string;
  bags: Bag[];
  value: { train_bags: string[]; validation_bags: string[] };
  onChange: (v: { train_bags: string[]; validation_bags: string[] }) => void;
}) {
  const [split, setSplit] = useState<{
      splits: Record<string, string[]>;
    } | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ splits: Record<string, string[]> }>(
      `/splits?strategy=${strategy}&train_vehicle=${vehicle}`,
    )
      .then((v) => {
        if (active) {
          setSplit(v);
          onChange({ train_bags: [], validation_bags: [] });
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [strategy, vehicle]);
  return (
    <details className="model-settings">
      <summary>Ограничить train / validation для короткого прогона</summary>
      <p className="help">
        Без выбора используются все поездки соответствующей выборки. Test сюда
        не попадает.
      </p>
      {error && <p>{error}</p>}
      <div className="form-grid">
        {(["train", "validation"] as const).map((s) => {
          const key = `${s}_bags` as "train_bags" | "validation_bags";
          return (
            <label className="form-field" key={s}>
              {s} · выбрано {value[key].length || "все"}
              <select
                multiple
                className="bag-multiselect"
                value={value[key]}
                onChange={(e) =>
                  onChange({
                    ...value,
                    [key]: Array.from(e.target.selectedOptions, (o) => o.value),
                  })
                }
              >
                {split?.splits[s].map((id) => (
                  <option key={id} value={id}>
                    {id} ·{" "}
                    {Math.round(
                      (bags.find((b) => b.id === id)?.duration_s || 0) / 60,
                    )}{" "}
                    мин
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="quiet"
                onClick={() => onChange({ ...value, [key]: [] })}
              >
                Использовать все
              </button>
            </label>
          );
        })}
      </div>
    </details>
  );
}
