import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import App from '../src/App.vue'

describe('App', () => {
  it('renders product title', () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    const wrapper = mount(App, { global: { plugins: [ElementPlus, router] } })
    expect(wrapper.text()).toContain('GroundLens')
    expect(wrapper.text()).toContain('检测任务')
  })
})
