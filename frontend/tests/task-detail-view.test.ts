import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, vi } from 'vitest'
import TaskDetailView from '../src/views/TaskDetailView.vue'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('../src/api', () => ({ api: apiMocks }))

const task = {
  id: 'task-1',
  name: '比较进度测试',
  knowledge_base_id: 'kb-1',
  status: 'completed',
  model_name: 'deepseek-v4-flash',
  total_count: 1,
  completed_count: 1,
  error_count: 0,
  created_at: '2026-08-08T00:00:00Z',
  updated_at: '2026-08-08T00:00:00Z',
  items: [],
}
let evaluationData: unknown[] = []

class MockEventSource {
  static instances: MockEventSource[] = []
  listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>()
  onerror: (() => void) | null = null
  closed = false

  constructor(public url: string) {
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    const listeners = this.listeners.get(type) || []
    listeners.push(listener)
    this.listeners.set(type, listeners)
  }

  emit(type: string, data: object) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) })
    for (const listener of this.listeners.get(type) || []) listener(event)
  }

  close() {
    this.closed = true
  }
}

describe('TaskDetailView', () => {
  beforeEach(() => {
    evaluationData = []
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.get.mockImplementation((url: string) =>
      Promise.resolve({ data: url.includes('/evaluations/') ? evaluationData : task }),
    )
  })

  it('shows the DeepSeek insight failure reason', async () => {
    evaluationData = [
      {
        id: 'evaluation-1',
        task_id: 'task-1',
        metrics: {
          recall: 0.8,
          accuracy: 0.3,
          evaluated_count: 20,
          tp: 5,
          tn: 1,
          fn: 1,
          fp: 13,
        },
        ground_truth_count: 20,
        insight_status: 'fallback',
        insight_error: 'DeepSeek 连续三次未返回有效建议',
        created_at: '2026-08-08T00:00:00Z',
        analyses: [],
        suggestions: [],
      },
    ]
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/tasks/:id', component: TaskDetailView }],
    })
    await router.push('/tasks/task-1')
    await router.isReady()
    const wrapper = mount(TaskDetailView, { global: { plugins: [ElementPlus, router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('AI 优化建议生成失败')
    expect(wrapper.text()).toContain('DeepSeek 连续三次未返回有效建议')
    expect(wrapper.text()).toContain('Accuracy 正确率')
    expect(wrapper.text()).toContain('30.0%')
    expect(wrapper.text()).toContain('正确 6 / 20 条')
    expect(wrapper.text()).not.toContain('Precision 准确率')
    wrapper.unmount()
  })

  it('shows loading and comparison progress until evaluation completes', async () => {
    apiMocks.post.mockImplementation(
      (
        _url: string,
        _data: FormData,
        config: { onUploadProgress: (event: { loaded: number; total: number }) => void },
      ) => {
        config.onUploadProgress({ loaded: 100, total: 100 })
        return Promise.resolve({
          data: {
            id: 'evaluation-stream',
            task_id: 'task-1',
            metrics: { recall: 1, accuracy: 1, evaluated_count: 1, tp: 1, tn: 0 },
            ground_truth_count: 1,
            insight_status: 'pending',
            insight_error: null,
            insight_progress: 10,
            insight_stage: '人工标注校验完成，已创建后台评测',
            insight_events: [],
            created_at: '2026-08-08T00:00:00Z',
            analyses: [],
            suggestions: [],
          },
        })
      },
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/tasks/:id', component: TaskDetailView }],
    })
    await router.push('/tasks/task-1')
    await router.isReady()
    const wrapper = mount(TaskDetailView, { global: { plugins: [ElementPlus, router] } })
    await flushPromises()

    const selectFile = wrapper.findComponent({ name: 'ElUpload' }).props('onChange') as (file: {
      raw: File
    }) => void
    selectFile({ raw: new File(['[]'], 'ground-truth.json', { type: 'application/json' }) })
    await flushPromises()
    expect(wrapper.text()).toContain('已选择：ground-truth.json')
    expect(wrapper.text()).toContain('重新选择')

    const replacement = new File(['[]'], 'correct-ground-truth.json', {
      type: 'application/json',
    })
    const replaceFile = wrapper.findComponent({ name: 'ElUpload' }).props('onExceed') as (
      files: File[],
    ) => void
    replaceFile([replacement])
    await flushPromises()
    expect(wrapper.text()).toContain('已选择：correct-ground-truth.json')
    expect(wrapper.text()).not.toContain('已选择：ground-truth.json')
    const compareButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始比对'))
    expect(compareButton).toBeDefined()

    await compareButton!.trigger('click')
    await flushPromises()

    const loadingButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('正在比较'))
    expect(loadingButton).toBeDefined()
    expect(loadingButton!.classes()).toContain('is-loading')
    expect(wrapper.text()).toContain('人工标注比较进度')
    expect(wrapper.text()).toContain('人工标注校验完成，已创建后台评测')
    const stream = MockEventSource.instances[0]
    expect(stream.url).toBe('/api/v1/evaluations/evaluation-stream/events')

    stream.emit('progress', {
      sequence: 2,
      stage: '发现 2 条误判，正在准备分析上下文',
      progress: 35,
      status: 'running',
      created_at: '2026-08-08T00:00:01Z',
    })
    await flushPromises()
    expect(wrapper.text()).toContain('发现 2 条误判，正在准备分析上下文')
    expect(wrapper.text()).toContain('35%')

    evaluationData = [
      {
        id: 'evaluation-stream',
        task_id: 'task-1',
        metrics: { recall: 1, accuracy: 1, evaluated_count: 1, tp: 1, tn: 0 },
        ground_truth_count: 1,
        insight_status: 'completed',
        insight_error: null,
        insight_progress: 100,
        insight_stage: '已保存 2 条误判分析和 2 条优化建议',
        insight_events: [],
        created_at: '2026-08-08T00:00:00Z',
        analyses: [],
        suggestions: [],
      },
    ]
    stream.emit('complete', { status: 'completed' })
    await flushPromises()

    expect(wrapper.text()).toContain('已保存 2 条误判分析和 2 条优化建议')
    expect(stream.closed).toBe(true)
    const completedButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始比对'))
    expect(completedButton).toBeDefined()
    expect(completedButton!.classes()).not.toContain('is-loading')
    wrapper.unmount()
  })

  it('reconnects to an unfinished evaluation after refreshing the page', async () => {
    const runningEvaluation = {
      id: 'evaluation-running',
      task_id: 'task-1',
      metrics: { recall: 0.8, accuracy: 0.8, evaluated_count: 20, tp: 16, tn: 0 },
      ground_truth_count: 20,
      insight_status: 'running',
      insight_error: null,
      insight_progress: 52,
      insight_stage: 'DeepSeek 已返回结果，正在校验完整优化方案',
      insight_events: [
        {
          sequence: 1,
          stage: '正在请求 DeepSeek 生成误判分析与优化建议（第 1/3 次）',
          progress: 45,
          status: 'running',
          created_at: '2026-08-08T00:00:01Z',
        },
      ],
      created_at: '2026-08-08T00:00:00Z',
      analyses: [],
      suggestions: [],
    }
    evaluationData = [runningEvaluation]
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/tasks/:id', component: TaskDetailView }],
    })
    await router.push('/tasks/task-1')
    await router.isReady()
    const wrapper = mount(TaskDetailView, { global: { plugins: [ElementPlus, router] } })
    await flushPromises()

    expect(MockEventSource.instances).toHaveLength(1)
    expect(wrapper.text()).toContain('DeepSeek 已返回结果，正在校验完整优化方案')
    expect(wrapper.text()).toContain('正在请求 DeepSeek 生成误判分析与优化建议（第 1/3 次）')

    evaluationData = [{ ...runningEvaluation, insight_status: 'completed', insight_progress: 100 }]
    MockEventSource.instances[0].emit('complete', { status: 'completed' })
    await flushPromises()

    expect(MockEventSource.instances[0].closed).toBe(true)
    wrapper.unmount()
  })

  it('applies the complete suggestion plan through one endpoint', async () => {
    evaluationData = [
      {
        id: 'evaluation-plan',
        task_id: 'task-1',
        metrics: { recall: 1, accuracy: 0.5, evaluated_count: 2, tp: 1, tn: 0, fn: 0, fp: 1 },
        ground_truth_count: 2,
        insight_status: 'completed',
        insight_error: null,
        optimization_context: {
          history_round_count: 3,
          recurring_mismatches: [
            {
              expected_category: '信息编造',
              predicted_category: '事实信息编造',
              round_count: 3,
              case_ids: ['h07'],
            },
          ],
          regression_cases: [],
        },
        created_at: '2026-08-08T00:00:00Z',
        analyses: [
          {
            id: 'analysis-1',
            input_id: 'h07',
            error_type: 'false_positive',
            human_category: '信息编造',
            predicted_category: '事实信息编造',
            reason: '分类名称不一致',
            likely_cause: '旧分类持续抢占',
            evidence_summary: '',
          },
        ],
        suggestions: [
          {
            id: 'suggestion-1',
            category_id: 'category-1',
            action: 'archive',
            target_category_name: '政策与优惠错误',
            reason: '由细分类替代',
            proposed_changes: {},
            impact_analysis: {
              resolved_case_ids: ['h07'],
              historical_evidence: { round_count: 3 },
              regression_risk: 'high',
              regression_risk_reason: '归档前需确认没有其它正确用途',
            },
            status: 'pending',
            created_at: '2026-08-08T00:00:00Z',
            decided_at: null,
          },
        ],
      },
    ]
    apiMocks.post.mockResolvedValue({ data: [] })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/tasks/:id', component: TaskDetailView }],
    })
    await router.push('/tasks/task-1')
    await router.isReady()
    const wrapper = mount(TaskDetailView, { global: { plugins: [ElementPlus, router] } })
    await flushPromises()

    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()

    expect(apiMocks.post).toHaveBeenCalledWith('/evaluations/evaluation-plan/suggestions/apply-all')
    expect(wrapper.text()).toContain('只能整套采纳或全部忽略')
    expect(wrapper.text()).toContain('已结合 3 轮评测历史')
    expect(wrapper.text()).toContain('事实信息编造 → 信息编造（3 轮，h07）')
    expect(wrapper.text()).toContain('高风险')
    expect(wrapper.text()).toContain('预计改善：h07')
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('方案包含高回归风险项'),
      '采纳整套优化方案',
      expect.any(Object),
    )
    wrapper.unmount()
  })
})
