import { describe, expect, it } from 'vitest'

import {
  normalizeMarcelOpenString,
  pathFromMarcelDeepLink,
  pathFromOpenDeepLink,
  resolveMarcelOpenPath
} from './marcel-open-target'

describe('normalizeMarcelOpenString', () => {
  it('accepts hash-router paths and strips a leading hash', () => {
    expect(normalizeMarcelOpenString('/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeMarcelOpenString('#/index-network/intent/1')).toBe('/index-network/intent/1')
  })

  it('maps plugin-scoped marcel:// deep links to the same path', () => {
    expect(normalizeMarcelOpenString('marcel://index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeMarcelOpenString('marcel://index-network/intent/1?focus=true')).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('maps marcel://open/… deep links by stripping the open host', () => {
    expect(normalizeMarcelOpenString('marcel://open/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeMarcelOpenString('marcel://open/settings/plugins')).toBe('/settings/plugins')
  })

  it('rejects reserved marcel kinds and unsafe paths', () => {
    expect(normalizeMarcelOpenString('marcel://blueprint/morning-brief')).toBeNull()
    expect(normalizeMarcelOpenString('marcel://plugin/install')).toBeNull()
    expect(normalizeMarcelOpenString('https://example.com/x')).toBeNull()
    expect(normalizeMarcelOpenString('/../etc/passwd')).toBeNull()
    expect(normalizeMarcelOpenString('index-network')).toBeNull()
  })
})

describe('resolveMarcelOpenPath', () => {
  it('merges structured path + params', () => {
    expect(resolveMarcelOpenPath({ path: '/index-network/intent/1', params: { focus: 'true' } })).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('resolves href the same as a bare string', () => {
    expect(resolveMarcelOpenPath({ href: 'marcel://index-network/intent/1' })).toBe('/index-network/intent/1')
  })
})

describe('pathFromMarcelDeepLink', () => {
  it('builds the navigate path from a plugin-scoped deep-link payload', () => {
    expect(pathFromMarcelDeepLink('index-network', 'intent/1')).toBe('/index-network/intent/1')
  })

  it('builds the navigate path from marcel://open/… payloads', () => {
    expect(pathFromOpenDeepLink('index-network/intent/1')).toBe('/index-network/intent/1')
    expect(pathFromMarcelDeepLink('open', 'agent/42')).toBe('/agent/42')
  })

  it('ignores reserved kinds', () => {
    expect(pathFromMarcelDeepLink('blueprint', 'morning-brief')).toBeNull()
    expect(pathFromMarcelDeepLink('plugin', 'install')).toBeNull()
  })
})
