import { useEffect, useState } from "react";
import App from "./App";
import ResearchPage from "./ResearchPage";
import "./research-workspace.css";

/** Preserve the original application and its selected runs when switching views. */
export default function ResearchWorkspace() {
  const [research, setResearch] = useState(() => window.location.hash === "#research");
  useEffect(() => {
    const changed = () => setResearch(window.location.hash === "#research");
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return (
    <div className="research-workspace">
      <nav aria-label="Разделы Tram Lab" className="research-navigation">
        <a href="#lab" aria-current={research ? undefined : "page"}>Лаборатория</a>
        <a href="#research" aria-current={research ? "page" : undefined}>Маршрут и GNSS</a>
        <span>Исследовательский режим · основной v8 не заменён</span>
      </nav>
      <div className="research-view" style={{ display: research ? "none" : "block" }}><App /></div>
      <div className="research-view" style={{ display: research ? "block" : "none" }}><ResearchPage /></div>
    </div>
  );
}
