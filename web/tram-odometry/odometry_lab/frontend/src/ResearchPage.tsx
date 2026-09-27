import { useTheme } from "./ThemeContext";

/** Same-origin, dependency-free research view; all computations use the lab API. */
export default function ResearchPage() {
  const { theme } = useTheme();
  return (
    <iframe
      title="Маршрут и редкие GNSS"
      src={`/api/v1/research/page?theme=${encodeURIComponent(theme)}`}
      style={{ width: "100%", height: "100%", display: "block", border: 0 }}
    />
  );
}
