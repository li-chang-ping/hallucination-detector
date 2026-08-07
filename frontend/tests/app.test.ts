import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'

describe('App', () => {
  it('renders product title', () => {
    const wrapper = mount(App, { global: { plugins: [ElementPlus] } })
    expect(wrapper.text()).toContain('GroundLens')
  })
})
