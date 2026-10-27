import { apiGet } from './client'

/**
 * 量化分析 API（/api/us-analytics/* 与 /api/hk-analytics/*）。
 * US/HK 两市场共用同一套 tab 组件，仅 URL 前缀不同；后端返回结构一致：
 * 时序类端点返回 { dates: string[], ...指标序列 }，截面类端点返回 { rows: [...] }。
 * 时间一律 YYYY-MM-DD 字符串。
 */
export interface AnalyticsApi {
  fetch<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T>
  symbols(): Promise<{ symbols: string[] }>
}

function makeAnalyticsApi(prefix: string): AnalyticsApi {
  const fetch = <T,>(
    path: string,
    params?: Record<string, string | number | undefined>,
  ): Promise<T> => {
    const clean: Record<string, unknown> = {}
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') clean[k] = v
      }
    }
    return apiGet<T>(`${prefix}${path}`, clean)
  }
  return {
    fetch,
    symbols: () => fetch<{ symbols: string[] }>('/symbols'),
  }
}

export const usAnalyticsApi = makeAnalyticsApi('/us-analytics')
export const hkAnalyticsApi = makeAnalyticsApi('/hk-analytics')

/** 按市场标识取 API（"hk" → 港股，其余 → 美股）。tab 组件经 mk prop 透传。 */
export function analyticsApiFor(mk?: string): AnalyticsApi {
  return mk === 'hk' ? hkAnalyticsApi : usAnalyticsApi
}

/** 兼容旧调用：美股分析 API 直连。 */
export function fetchUsAnalytics<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
): Promise<T> {
  return usAnalyticsApi.fetch<T>(path, params)
}

export function fetchUsAnalyticsSymbols(): Promise<{ symbols: string[] }> {
  return usAnalyticsApi.symbols()
}
