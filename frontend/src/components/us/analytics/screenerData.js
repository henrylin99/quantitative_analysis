// 美股扫描器六维 tab 的共享数据源：/screener/base 单端点 payload 的
// module-level promise 缓存。6 个 tab 挂载时共享同一次请求（切 tab 不重复
// 取数；请求失败会释放缓存以便重试）。后端有缓存，本模块只做前端去重。
import { useEffect, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";

let cached = null;

export function loadScreenerBase() {
  if (!cached) {
    cached = fetchUsAnalytics("/screener/base")
      .then((res) => res?.rows || [])
      .catch((e) => { cached = null; throw e; });
  }
  return cached;
}

// Hook：{ rows, loaded, error, tradeDate }。所有扫描 tab 用同一份截面。
export function useScreenerBase() {
  const [state, setState] = useState({ rows: [], loaded: false, error: null });
  useEffect(() => {
    let alive = true;
    loadScreenerBase()
      .then((rows) => { if (alive) setState({ rows, loaded: true, error: null }); })
      .catch((e) => { if (alive) setState({ rows: [], loaded: true, error: e?.message || String(e) }); });
    return () => { alive = false; };
  }, []);
  return {
    ...state,
    tradeDate: state.rows[0]?.trade_date || null,
  };
}
