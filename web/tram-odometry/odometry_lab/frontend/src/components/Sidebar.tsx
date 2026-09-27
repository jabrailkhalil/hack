import { useState } from "react";
import { TrainFront } from "lucide-react";
import { useTheme } from "../ThemeContext";

export type Section =
  | "analysis"
  | "experiments"
  | "data"
  | "models"
  | "training";

interface SidebarProps {
  current: Section;
  connected: boolean;
  onChange: (s: Section) => void;
  onNewExperiment: () => void;
}

const navItems: { id: Section; label: string; icon: string }[] = [
  { id: "analysis", label: "Анализ", icon: "◈" },
  { id: "experiments", label: "Эксперименты", icon: "⊡" },
  { id: "data", label: "Данные", icon: "⊟" },
  { id: "models", label: "Модели", icon: "⬡" },
  { id: "training", label: "Обучение и подбор", icon: "⊕" },
];

export default function Sidebar({
  current,
  onChange,
  onNewExperiment,
  connected,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const { theme, toggle } = useTheme();

  return (
    <div
      className="design-sidebar flex flex-col border-r shrink-0 transition-all duration-200"
      style={{
        width: collapsed ? 48 : 200,
        background: "var(--sidebar-bg)",
        borderColor: "var(--border)",
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-2 px-3 py-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div
          className="w-6 h-6 rounded flex items-center justify-center shrink-0"
          style={{ background: "var(--accent)" }}
        >
          <TrainFront size={20} style={{ color: "var(--accent-fg)" }} />
        </div>
        {!collapsed && (
          <span
            className="font-semibold text-[13px] tracking-tight"
            style={{ color: "var(--text)" }}
          >
            Tram Lab
          </span>
        )}
        <button
          aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto text-sm leading-none transition-colors"
          style={{ color: "var(--text-faint)" }}
        >
          {collapsed ? "›" : "‹"}
        </button>
      </div>

      {/* New Experiment */}
      <div
        className="px-2 py-2"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <button
          aria-label="Новый эксперимент"
          onClick={onNewExperiment}
          className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-[12px] font-medium transition-colors"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          onMouseEnter={(e) =>
            (e.currentTarget.style.background = "var(--accent-h)")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.background = "var(--accent)")
          }
        >
          <span className="shrink-0 text-base leading-none">+</span>
          {!collapsed && <span>Новый эксперимент</span>}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-1">
        {navItems.map((item) => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              aria-label={item.label}
              aria-current={active ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] transition-colors border-r-2"
              style={{
                borderColor: active ? "var(--accent)" : "transparent",
                background: active ? "var(--bg)" : "transparent",
                color: active ? "var(--accent)" : "var(--text-muted)",
                fontWeight: active ? 500 : 400,
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  e.currentTarget.style.background = "var(--bg)";
                  e.currentTarget.style.color = "var(--text)";
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = "var(--text-muted)";
                }
              }}
            >
              <span className="text-base leading-none shrink-0">
                {item.icon}
              </span>
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Theme toggle */}
      <div
        className="px-3 py-2"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <button
          onClick={toggle}
          title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          className="flex items-center gap-2 w-full transition-colors rounded px-1 py-1"
          style={{ color: "var(--text-faint)" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
          onMouseLeave={(e) =>
            (e.currentTarget.style.color = "var(--text-faint)")
          }
        >
          <span className="text-base leading-none shrink-0">
            {theme === "dark" ? "☀" : "☽"}
          </span>
          {!collapsed && (
            <span className="text-[11px]">
              {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            </span>
          )}
        </button>
      </div>

      {/* Connection indicator */}
      <div
        className={`px-3 py-2 flex items-center gap-2 ${collapsed ? "justify-center" : ""}`}
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? "bg-green-500" : "bg-red-500"}`}
        />
        {!collapsed && (
          <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>
            {connected ? "Локальный сервис" : "Нет соединения"}
          </span>
        )}
      </div>
    </div>
  );
}
