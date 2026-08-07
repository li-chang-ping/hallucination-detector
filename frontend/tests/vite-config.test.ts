// @vitest-environment node

import config from '../vite.config'

describe('Vite configuration', () => {
  it('loads Vue files and refuses an ambiguous development port', () => {
    const plugins = Array.isArray(config.plugins) ? config.plugins.flat() : []

    expect(plugins.some((plugin) => plugin && 'name' in plugin && plugin.name === 'vite:vue')).toBe(
      true,
    )
    expect(config.server).toMatchObject({
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
    })
  })
})
