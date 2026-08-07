import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, vi } from 'vitest'
import CategoriesView from '../src/views/CategoriesView.vue'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() }))

vi.mock('../src/api', () => ({ api: apiMocks }))

describe('CategoriesView', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.put.mockReset()
    apiMocks.get.mockResolvedValue({
      data: [
        {
          id: 'category-1',
          name: '政策错误',
          description: '政策与证据冲突',
          default_severity: 'high',
          prompt_guidance: '严格核对条件',
          is_active: true,
          is_archived: false,
        },
      ],
    })
  })

  it('restores the switch when enabling state update fails', async () => {
    apiMocks.put.mockRejectedValue(new Error('分类更新失败'))
    const errorMessage = vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    const wrapper = mount(CategoriesView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.find('.el-switch').trigger('click')
    await flushPromises()

    expect(apiMocks.put).toHaveBeenCalledWith('/categories/category-1', { is_active: false })
    expect(wrapper.find('.el-switch').classes()).toContain('is-checked')
    expect(errorMessage).toHaveBeenCalledWith('分类更新失败')
  })
})
