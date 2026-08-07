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
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
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
