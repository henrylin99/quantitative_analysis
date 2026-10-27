// 美股个股风险 —— 个股级风险分析：尾部风险 / 回撤分析 / 贝塔与系统性风险 /
// 配对交易·协整 / 风险调整收益排名 / 有效下注数·可分散性 / 流动性·交易成本。
// 数据由 /api/us-analytics/risk/* 在后端宽表上计算，前端只做展示。
import { useState } from "react";
import "./us-tv.css";

import TailRiskTab from "../../components/us/analytics/TailRiskTab.jsx";
import DrawdownTab from "../../components/us/analytics/DrawdownTab.jsx";
import BetaTab from "../../components/us/analytics/BetaTab.jsx";
import PairsTab from "../../components/us/analytics/PairsTab.jsx";
import SharpeTab from "../../components/us/analytics/SharpeTab.jsx";
import EffBetsTab from "../../components/us/analytics/EffBetsTab.jsx";
import LiquidityTab from "../../components/us/analytics/LiquidityTab.jsx";

const TABS = [
  { id: "tailrisk", label: "尾部风险", Component: TailRiskTab },
  { id: "drawdown", label: "回撤分析", Component: DrawdownTab },
  { id: "beta", label: "贝塔与系统性风险", Component: BetaTab },
  { id: "pairs", label: "配对交易·协整", Component: PairsTab },
  { id: "sharpe", label: "风险调整收益排名", Component: SharpeTab },
  { id: "effbets", label: "有效下注数·可分散性", Component: EffBetsTab },
  { id: "liquidity", label: "流动性·交易成本", Component: LiquidityTab },
];

export default function UsRiskAnalyticsPage() {
  const [tab, setTab] = useState(TABS[0].id);
  const Current = TABS.find((t) => t.id === tab).Component;
  return (
    <div className="us-tv" style={{ minHeight: "100%", padding: "14px 18px" }}>
      <div className="tv-page-head">
        <h2 style={{ margin: 0, fontSize: 17 }}>个股风险</h2>
        <span style={{ color: "var(--tv-text-dim)", fontSize: 12 }}>
          个股级风险与依赖结构 · 数据源为本池日线宽表
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
