import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { storedBoolean } from '@/lib/storage'

import { $keepAwake, setKeepAwake } from './keep-awake'

const KEY = 'marcel.desktop.keepAwake.v1'
const desktopWindow = window as unknown as { marcelDesktop?: Window['marcelDesktop'] }
const initialMarcelDesktop = desktopWindow.marcelDesktop
const setKeepAwakeBridge = vi.fn()

beforeEach(() => {
  desktopWindow.marcelDesktop = { setKeepAwake: setKeepAwakeBridge } as unknown as Window['marcelDesktop']
  setKeepAwake(false)
  setKeepAwakeBridge.mockClear()
})

afterEach(() => {
  desktopWindow.marcelDesktop = initialMarcelDesktop
})

describe('keep-awake store', () => {
  it('persists the pref and mirrors it to the main process', () => {
    setKeepAwake(true)
    expect($keepAwake.get()).toBe(true)
    expect(storedBoolean(KEY, false)).toBe(true)
    expect(setKeepAwakeBridge).toHaveBeenLastCalledWith(true)

    setKeepAwake(false)
    expect(storedBoolean(KEY, true)).toBe(false)
    expect(setKeepAwakeBridge).toHaveBeenLastCalledWith(false)
  })
})
