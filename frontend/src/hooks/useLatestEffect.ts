import { useEffect, useRef } from 'react'
import type { DependencyList } from 'react'

/**
 * 带竞态防护的 useEffect 数据加载。
 *
 * 页面里普遍存在 fire-and-forget 的 `.then(setX)` 加载模式：快速切换
 * 依赖（如 StockDetailPage 的 historyLimit、tsCode）或快速切页时，
 * 慢的旧响应会覆盖新数据，或对已卸载组件 setState。
 *
 * 本 hook 给任务闭包发一个取消探针：组件卸载或依赖变化后，旧闭包的
 * isCancelled() 变为 true，调用方据此丢弃过期响应：
 *
 *   useLatestEffect(async (isCancelled) => {
 *     setHistoryLoading(true)
 *     try {
 *       const data = await fetchStockHistory(tsCode, limit)
 *       if (!isCancelled()) setHistory(data)
 *     } finally {
 *       if (!isCancelled()) setHistoryLoading(false)
 *     }
 *   }, [tsCode, limit])
 *
 * 注意：这只丢弃过期回调，不中止底层网络请求；如需真正取消请传
 * AbortSignal（当前 api 层未暴露，单机场景下丢弃回调已足够）。
 */
export function useLatestEffect(
  task: (isCancelled: () => boolean) => void,
  deps: DependencyList,
): void {
  const seqRef = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const seq = ++seqRef.current
    const isCancelled = () => seqRef.current !== seq
    task(isCancelled)
    return () => {
      // 卸载或依赖变化：令旧闭包的探针失效
      seqRef.current += 1
    }
  }, deps)
}
