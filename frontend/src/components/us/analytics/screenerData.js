// 扫描器各维度 tab 的共享数据源：/screener/base 单端点 payload 的
// module-level promise 缓存（按市场 mk 分键，US/HK 互不串缓存）。
// 同市场的 tab 挂载时共享同一次请求（切 tab 不重复取数；请求失败会
// 释放缓存以便重试）。后端有缓存，本模块只做前端去重。
import { useEffect, useState } from "react";
import { analyticsApiFor } from "../../../api/usAnalytics";

const caches = {}; // mk -> Promise<rows>

export function loadScreenerBase(mk = "us") {
  if (!caches[mk]) {
    caches[mk] = analyticsApiFor(mk)
      .fetch("/screener/base")
      .then((res) => res?.rows || [])
      .catch((e) => { delete caches[mk]; throw e; });
  }
  return caches[mk];
}

// Hook：{ rows, loaded, error, tradeDate }。同一市场的所有扫描 tab 用同一份截面。
export function useScreenerBase(mk = "us") {
  const [state, setState] = useState({ rows: [], loaded: false, error: null });
  useEffect(() => {
    let alive = true;
    setState({ rows: [], loaded: false, error: null });
    loadScreenerBase(mk)
      .then((rows) => { if (alive) setState({ rows, loaded: true, error: null }); })
      .catch((e) => { if (alive) setState({ rows: [], loaded: true, error: e?.message || String(e) }); });
    return () => { alive = false; };
  }, [mk]);
  return {
    ...state,
    tradeDate: state.rows[0]?.trade_date || null,
  };
}
