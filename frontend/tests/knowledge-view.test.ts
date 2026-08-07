import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { vi } from 'vitest'
import KnowledgeView from '../src/views/KnowledgeView.vue'

vi.mock('../src/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
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
    }),
  },
}))

describe('KnowledgeView', () => {
  it('shows the embedding model without implementation copy', async () => {
    const wrapper = mount(KnowledgeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('嵌入模型：qwen3-embedding:0.6b')
    expect(wrapper.text()).not.toContain('通过 Ollama 中文向量模型建立可追溯的检测证据')
  })
})
