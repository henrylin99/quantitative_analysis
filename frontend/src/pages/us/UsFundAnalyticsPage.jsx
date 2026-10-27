// 美股基本面与事件 —— 宏观叠加 / 基本面轨迹 / 行业·风格轮动 / 财报事件研究。
// 宏观序列与行业 ETF、财务长表来自 data/us_aux/*，事件研究配日线宽表。
import { useState } from "react";
import "./us-tv.css";

import MacroOverlayTab from "../../components/us/analytics/MacroOverlayTab.jsx";
import FundTrajectoryTab from "../../components/us/analytics/FundTrajectoryTab.jsx";
import RotationTab from "../../components/us/analytics/RotationTab.jsx";
import EventStudyTab from "../../components/us/analytics/EventStudyTab.jsx";

const TABS = [
  { id: "macro", label: "宏观叠加", Component: MacroOverlayTab },
  { id: "trajectory", label: "基本面轨迹", Component: FundTrajectoryTab },
  { id: "rotation", label: "行业·风格轮动", Component: RotationTab },
  { id: "eventstudy", label: "财报事件研究", Component: EventStudyTab },
];

export default function UsFundAnalyticsPage() {
  const [tab, setTab] = useState(TABS[0].id);
  const Current = TABS.find((t) => t.id === tab).Component;
  return (
    <div className="us-tv" style={{ minHeight: "100%", padding: "14px 18px" }}>
      <div className="tv-page-head">
        <h2 style={{ margin: 0, fontSize: 17 }}>基本面与事件</h2>
        <span style={{ color: "var(--tv-text-dim)", fontSize: 12 }}>
          宏观敏感度 / 财务轨迹 / 行业轮动 / 财报事件
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
