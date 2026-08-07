import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { beforeEach, vi } from 'vitest'
import KnowledgeView from '../src/views/KnowledgeView.vue'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn() }))

vi.mock('../src/api', () => ({
  api: apiMocks,
}))

describe('KnowledgeView', () => {
  beforeEach(() => {
    apiMocks.get.mockResolvedValue({
      data: [
        {
          id: 'kb-1',
          name: '演示知识库',
          description: '测试数据',
          embedding_model: 'qwen3-embedding:0.6b',
          entry_count: 20,
          created_at: '2026-08-08T00:00:00Z',
        },
      ],
    })
    apiMocks.delete.mockReset()
  })

  it('shows the embedding model without implementation copy', async () => {
    const wrapper = mount(KnowledgeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('嵌入模型：qwen3-embedding:0.6b')
    expect(wrapper.text()).not.toContain('通过 Ollama 中文向量模型建立可追溯的检测证据')
  })

  it('shows the backend reason when deletion is blocked', async () => {
    apiMocks.delete.mockRejectedValue(new Error('该知识库正被 1 个未结束任务使用'))
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const errorMessage = vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    const wrapper = mount(KnowledgeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.find('.el-button--danger').trigger('click')
    await flushPromises()

    expect(errorMessage).toHaveBeenCalledWith('该知识库正被 1 个未结束任务使用')
  })
})
