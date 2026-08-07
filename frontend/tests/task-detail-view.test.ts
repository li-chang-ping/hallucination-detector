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

describe('TaskDetailView', () => {
  beforeEach(() => {
    evaluationData = []
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
    let resolvePost: (() => void) | undefined
    apiMocks.post.mockImplementation(
      (
        _url: string,
        _data: FormData,
        config: { onUploadProgress: (event: { loaded: number; total: number }) => void },
      ) => {
        config.onUploadProgress({ loaded: 100, total: 100 })
        return new Promise((resolve) => {
          resolvePost = () => resolve({ data: {} })
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
    expect(wrapper.text()).toContain('正在计算指标并分析误判')

    resolvePost?.()
    await flushPromises()

    expect(wrapper.text()).toContain('比较完成')
    const completedButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始比对'))
    expect(completedButton).toBeDefined()
    expect(completedButton!.classes()).not.toContain('is-loading')
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
        created_at: '2026-08-08T00:00:00Z',
        analyses: [],
        suggestions: [
          {
            id: 'suggestion-1',
            category_id: 'category-1',
            action: 'archive',
            target_category_name: '政策与优惠错误',
            reason: '由细分类替代',
            proposed_changes: {},
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
    wrapper.unmount()
  })
})
