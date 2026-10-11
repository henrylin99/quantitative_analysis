import { extractApiError, rawGet, rawPost } from './client'

// ================= 日频数据中心 /api/data-jobs（裸响应 {success,...}） =================
export interface DataJobDef {
  job_type: string
  group: string
  script_path: string
  display_name: string
  description: string
  dangerous: boolean
  dependencies: string[]
  default_params: Record<string, unknown>
  recommended_order: number
  source_name: string
  source_mode: string
  supports_incremental: boolean
}

export interface DataJobRun {
  id: number
  job_type: string
  status: 'pending' | 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
  progress: number
  progress_message: string | null
  params_json: string | null
  source_name: string | null
  source_mode: string | null
  snapshot_tag: string | null
  result_json: { stdout?: string; stderr?: string } | null
  error_message: string | null
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface WideTableStatus {
  exists: boolean
  wide_table_date: string | null
  source_dates: Record<string, string | null>
  should_update: boolean
  reason: string
  past_cutoff: boolean
}

export interface InitStatus {
  entrypoint: string
  database: {
    ok: boolean
    connected: boolean
    missing_tables: string[]
    empty_tables: string[]
    missing_parquet_assets: string[]
    empty_parquet_assets: string[]
    next_actions: string[]
  }
  data_jobs: { execution_mode: string }
}

export const fetchDataJobDefs = () => rawGet<{ success: boolean; jobs: DataJobDef[]; count: number }>('/data-jobs/jobs')

export const fetchDataJobRuns = (limit = 20) =>
  rawGet<{ success: boolean; runs: DataJobRun[]; count: number }>('/data-jobs/list', { limit })

export const fetchDataJobRun = (runId: number) => rawGet<{ success: boolean; run: DataJobRun }>(`/data-jobs/${runId}`)

export const submitDataJob = async (jobType: string, params: Record<string, unknown> = {}) => {
  try {
    return await rawPost<{ success: boolean; run_id: number; job_type: string; status: string }>(
      '/data-jobs/submit',
      { job_type: jobType, params },
      120_000,
    )
  } catch (e) {
    throw new Error(extractApiError(e, '任务提交失败'))
  }
}

export const fetchWideTableStatus = () => rawGet<{ success: boolean; status: WideTableStatus }>('/data-jobs/wide-table/status')

export const buildWideTable = async () => {
  try {
    return await rawPost<{ success: boolean; run_id: number }>('/data-jobs/wide-table/build', {}, 120_000)
  } catch (e) {
    throw new Error(extractApiError(e, '大宽表构建提交失败'))
  }
}

export const fetchInitStatus = () => rawGet<{ success: boolean; status: InitStatus }>('/data-jobs/init-status')

// ================= 盘后数据链路 =================

export interface PipelineFreshnessRow {
  table: string
  latest_date: string | null
  expected_date: string | null
  lag_trading_days: number | null
  ok: boolean
}

export interface PipelineStatus {
  enabled: boolean
  jobs: string[]
  running: boolean
  recent_runs: Array<{
    started_at: string
    finished_at: string | null
    is_trading_day: boolean
    ok: boolean
    message?: string
    steps: Array<{ job_type: string; run_id?: number; status?: string; message?: string; started_at: string; finished_at?: string }>
  }>
  freshness: {
    checked_at: string
    expected_date: string | null
    has_calendar: boolean
    tables: PipelineFreshnessRow[]
    lagged_tables: string[]
    all_fresh: boolean
  }
}

export const fetchPipelineStatus = () =>
  rawGet<{ success: boolean } & PipelineStatus>('/data-jobs/pipeline/status')

export const runPipeline = () =>
  rawPost<{ success: boolean; message?: string }>('/data-jobs/pipeline/run', {})

// ================= 分钟数据 /api/realtime-analysis/data（{success, data}） =================
export interface MinuteStats {
  total_stocks: number
  total_records: number
  latest_time: string | null
  earliest_time: string | null
  period_stats: Record<string, number>
}

export const fetchMinuteStats = async (): Promise<MinuteStats | null> => {
  try {
    const r = await rawGet<{ success: boolean; data: MinuteStats }>('/realtime-analysis/data/stats')
    return r.data ?? null
  } catch {
    return null
  }
}

export const syncMinuteData = (body: { ts_code: string; period_type: string; start_date: string; end_date: string; use_baostock?: boolean }) =>
  rawPost<{ success: boolean; message: string }>('/realtime-analysis/data/sync', body, 300_000)

export const syncMinuteAllPeriods = (body: { ts_code: string; start_date: string; end_date: string; use_baostock?: boolean }) =>
  rawPost<{ success: boolean; data: Record<string, { success: boolean }> }>('/realtime-analysis/data/sync-all-periods', body, 300_000)

export const syncMinuteMultiple = (body: {
  stock_list: string[]
  period_type: string
  start_date: string
  end_date: string
  batch_size: number
  use_baostock?: boolean
}) =>
  rawPost<{ success: boolean; message: string; success_stocks: number; failed_stocks: number; total_data_count: number }>(
    '/realtime-analysis/data/sync-multiple',
    body,
    600_000,
  )

export const fetchMinuteSyncStatus = async (tsCode: string, periodType: string) => {
  const r = await rawGet<{
    success: boolean
    data: {
      has_data: boolean
      data_count: number
      latest_time: string | null
      earliest_time: string | null
      missing_count: number
      completeness: number
      status: string
      message: string
    }
  }>('/realtime-analysis/data/sync-status', { ts_code: tsCode, period_type: periodType })
  return r.data
}

export const aggregateMinuteData = (body: { ts_code: string; source_period: string; target_period: string }) =>
  rawPost<{ success: boolean; message: string }>('/realtime-analysis/data/aggregate', body, 300_000)

export const fetchMinuteQuality = async (tsCode: string, periodType: string, hours: number) => {
  const r = await rawGet<{
    success: boolean
    data: {
      status: string
      message: string
      data_count: number
      missing_count: number
      completeness: number
      latest_time: string | null
      earliest_time: string | null
    }
  }>('/realtime-analysis/data/quality', { ts_code: tsCode, period_type: periodType, hours })
  return r.data
}

export const fetchMinuteStockList = async (): Promise<string[]> => {
  const r = await rawGet<{ success: boolean; data: string[]; count: number }>('/realtime-analysis/data/stock-list')
  return r.data ?? []
}

// ================= 存储治理（存储看板 / factor_values 审计与清理） =================
export interface StorageDirInfo {
  name: string
  size_bytes: number
  files: number
}

export interface StorageOverview {
  data_dir: string
  total_bytes: number
  dirs: StorageDirInfo[]
  factor_values: {
    partitions: number
    oldest?: string
    latest?: string
    size_bytes?: number
    avg_partition_bytes?: number
    growth_per_month_bytes?: number
  }
}

export interface FactorValuesAudit {
  partitions_total: number
  oldest?: string
  latest?: string
  latest_size_bytes?: number
  factor_rows: { factor_id: string; rows: number }[]
  degenerate: { factor_id: string; rows: number }[]
}

export interface FactorValuesCleanupResult {
  success: boolean
  message?: string
  dry_run: boolean
  retention_days: number
  cutoff: string
  latest: string
  candidate_count: number
  reclaim_bytes: number
  remaining_partitions?: number
  deleted_count?: number
  deleted?: string[]
  candidates: { partition: string; trade_date: string; size_bytes: number }[]
}

export const fetchStorageOverview = () =>
  rawGet<{ data: StorageOverview }>('/datasources/storage-overview')

export const fetchFactorValuesAudit = () =>
  rawGet<{ data: FactorValuesAudit }>('/datasources/factor-values-audit')

export const runFactorValuesCleanup = (retentionDays: number, confirm: boolean) =>
  rawPost<{ data: FactorValuesCleanupResult }>('/datasources/factor-values-cleanup', {
    retention_days: retentionDays,
    confirm,
  })

// ================= 全市场分钟线同步 /api/realtime-analysis/data/market-sync =================

export interface MinuteMarketSyncProgress {
  mode: 'incremental' | 'backfill' | null
  run_id: string | null
  total: number
  done: number
  failed: number
  running: boolean
  cooldown: boolean
  started_at: string | null
  updated_at: string | null
  finished_at: string | null
  last_message: string | null
}

export const fetchMinuteMarketSyncStatus = () =>
  rawGet<{ data: MinuteMarketSyncProgress }>('/realtime-analysis/data/market-sync/status')

export const runMinuteMarketSync = (mode: 'incremental' | 'backfill') =>
  rawPost<{ success: boolean; message: string }>('/realtime-analysis/data/market-sync/run', { mode })
