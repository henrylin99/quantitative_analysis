import { apiGet } from './client'

/**
 * 美股量化分析 API（/api/us-analytics/*）。
 * 后端返回结构与开源参考实现保持一致：时序类端点返回
 * { dates: string[], ...指标序列 }，截面类端点返回 { rows: [...] }。
 * 时间一律 YYYY-MM-DD 字符串。
 */
export function fetchUsAnalytics<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
): Promise<T> {
  const clean: Record<string, unknown> = {}
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') clean[k] = v
    }
  }
  return apiGet<T>(`/us-analytics${path}`, clean)
}

export function fetchUsAnalyticsSymbols(): Promise<{ symbols: string[] }> {
  return fetchUsAnalytics('/symbols')
}
