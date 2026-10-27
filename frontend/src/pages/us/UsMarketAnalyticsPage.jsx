// 美股市场统计 —— 市场级日频衍生指标：市场宽度时序 / 相对强度排名 / 波动率体制 /
// 波动率锥 / 截面离散度 / 均值回归与持续性 / 季节性分析 / 隔夜与跳空。
// 数据由 /api/us-analytics/market/* 在后端宽表上计算，前端只做展示。
import { useState } from "react";
import "./us-tv.css";

import InternalsTab from "../../components/us/analytics/InternalsTab.jsx";
import RelStrengthTab from "../../components/us/analytics/RelStrengthTab.jsx";
import VolRegimeTab from "../../components/us/analytics/VolRegimeTab.jsx";
import VolConeTab from "../../components/us/analytics/VolConeTab.jsx";
import DispersionTab from "../../components/us/analytics/DispersionTab.jsx";
import PersistenceTab from "../../components/us/analytics/PersistenceTab.jsx";
import SeasonalityTab from "../../components/us/analytics/SeasonalityTab.jsx";
import OvernightTab from "../../components/us/analytics/OvernightTab.jsx";

const TABS = [
  { id: "internals", label: "市场宽度时序", Component: InternalsTab },
  { id: "relstrength", label: "相对强度排名", Component: RelStrengthTab },
  { id: "volregime", label: "波动率体制", Component: VolRegimeTab },
  { id: "volcone", label: "波动率锥", Component: VolConeTab },
  { id: "dispersion", label: "截面离散度", Component: DispersionTab },
  { id: "persistence", label: "均值回归与持续性", Component: PersistenceTab },
  { id: "seasonality", label: "季节性分析", Component: SeasonalityTab },
  { id: "overnight", label: "隔夜与跳空", Component: OvernightTab },
];

export default function UsMarketAnalyticsPage() {
  const [tab, setTab] = useState(TABS[0].id);
  const Current = TABS.find((t) => t.id === tab).Component;
  return (
    <div className="us-tv" style={{ minHeight: "100%", padding: "14px 18px" }}>
      <div className="tv-page-head">
        <h2 style={{ margin: 0, fontSize: 17 }}>市场统计</h2>
        <span style={{ color: "var(--tv-text-dim)", fontSize: 12 }}>
          市场级日频结构指标 · 数据源为本池日线宽表
        </span>
      </div>
      <div className="tv-tabbar" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === tab}
            className={"tv-tab" + (t.id === tab ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <Current />
    </div>
  );
}
