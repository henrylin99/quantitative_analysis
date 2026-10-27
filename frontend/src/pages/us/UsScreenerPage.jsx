// 美股扫描器 —— 单日截面六维打分：技术信号 / 风险与波动 / 动量与突破 /
// 蜡烛形态 / 估值 / 资金流向。后端 /api/us-analytics/screener/base 输出
// 截面列 + 现算指标与旗标，前端按维度做截面百分位打分与排序。
import { useState } from "react";
import "./us-tv.css";

import TechnicalScanTab from "../../components/us/analytics/TechnicalScanTab.jsx";
import RiskScanTab from "../../components/us/analytics/RiskScanTab.jsx";
import MomentumScanTab from "../../components/us/analytics/MomentumScanTab.jsx";
import CandleScanTab from "../../components/us/analytics/CandleScanTab.jsx";
import ValuationScanTab from "../../components/us/analytics/ValuationScanTab.jsx";
import MoneyflowScanTab from "../../components/us/analytics/MoneyflowScanTab.jsx";

const TABS = [
  { id: "technical", label: "技术信号", Component: TechnicalScanTab },
  { id: "risk", label: "风险与波动", Component: RiskScanTab },
  { id: "momentum", label: "动量与突破", Component: MomentumScanTab },
  { id: "candle", label: "蜡烛形态", Component: CandleScanTab },
  { id: "valuation", label: "估值", Component: ValuationScanTab },
  { id: "moneyflow", label: "资金流向", Component: MoneyflowScanTab },
];

export default function UsScreenerPage() {
  const [tab, setTab] = useState(TABS[0].id);
  const Current = TABS.find((t) => t.id === tab).Component;
  return (
    <div className="us-tv" style={{ minHeight: "100%", padding: "14px 18px" }}>
      <div className="tv-page-head">
        <h2 style={{ margin: 0, fontSize: 17 }}>美股扫描器</h2>
        <span style={{ color: "var(--tv-text-dim)", fontSize: 12 }}>
          单日截面六维打分 · 维度间独立排名，可排序筛选
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
