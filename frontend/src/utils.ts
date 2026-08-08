import type { CategoryMismatch, TaskStatus } from './types'

export const statusText: Record<TaskStatus, string> = {
  preparing: '准备证据',
  queued: '等待中',
  running: '检测中',
  paused: '已暂停',
  completed: '已完成',
  partial: '部分完成',
  failed: '失败',
  cancelled: '已取消',
}

export function percent(value: unknown): string {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`
}

export function formatTime(value: string): string {
  const timestamp = value.trim()
  // SQLite 会丢失 datetime 的时区标记，但后端约定所有时间均为 UTC。
  // 没有偏移量时补上 Z，避免浏览器把 UTC 误当成本地时间而少显示 8 小时。
  const normalized = /(?:z|[+-]\d{2}:?\d{2})$/i.test(timestamp) ? timestamp : `${timestamp}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

export function formatCategoryMismatches(items: CategoryMismatch[]): string {
  return items
    .map(
      (item) =>
        `${item.id}（人工：${item.expected_category}；模型：${item.predicted_category || '无分类'}）`,
    )
    .join('；')
}

const categoryFieldLabels: Record<string, string> = {
  name: '分类名称',
  description: '分类定义',
  prompt_guidance: '判定指引',
  default_severity: '默认严重度',
}

export function categoryChangeEntries(changes: Record<string, unknown>): [string, unknown][] {
  return Object.entries(changes).map(([key, value]) => [categoryFieldLabels[key] || key, value])
}

export function categorySnapshotStatus(snapshot: Record<string, unknown>): string {
  if (snapshot.is_archived) return '已归档'
  return snapshot.is_active ? '已启用' : '已停用'
}

export function isDialogCancelled(error: unknown): boolean {
  return error === 'cancel' || error === 'close'
}

export function taskProgress(total: number, completed: number, errors: number): number {
  if (total <= 0) return 0
  return Math.min(100, Math.round(((completed + errors) / total) * 100))
}

export function canCancelTask(status: string): boolean {
  return !['completed', 'partial', 'failed', 'cancelled'].includes(status)
}

export function canEvaluateTask(status: string): boolean {
  return ['completed', 'partial', 'failed', 'cancelled'].includes(status)
}
