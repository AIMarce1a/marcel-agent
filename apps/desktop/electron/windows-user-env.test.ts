import assert from 'node:assert/strict'

import { test } from 'vitest'

import { expandWindowsEnvRefs, parseRegQueryValue, readWindowsUserEnvVar } from './windows-user-env'

// ── parseRegQueryValue ─────────────────────────────────────────────────────

test('parseRegQueryValue extracts a REG_SZ value', () => {
  const out = ['', 'HKEY_CURRENT_USER\\Environment', '    MARCEL_HOME    REG_SZ    F:\\Marcel\\data', ''].join('\r\n')
  assert.equal(parseRegQueryValue(out, 'MARCEL_HOME'), 'F:\\Marcel\\data')
})

test('parseRegQueryValue matches the name case-insensitively', () => {
  const out = 'HKEY_CURRENT_USER\\Environment\r\n    Marcel_Home    REG_EXPAND_SZ    %USERPROFILE%\\h\r\n'
  assert.equal(parseRegQueryValue(out, 'MARCEL_HOME'), '%USERPROFILE%\\h')
})

test('parseRegQueryValue preserves spaces inside the value', () => {
  const out = '    MARCEL_HOME    REG_SZ    C:\\Program Files\\Marcel\r\n'
  assert.equal(parseRegQueryValue(out, 'MARCEL_HOME'), 'C:\\Program Files\\Marcel')
})

test('parseRegQueryValue returns null when the value line is absent', () => {
  const out = 'HKEY_CURRENT_USER\\Environment\r\n    Path    REG_SZ    C:\\x\r\n'
  assert.equal(parseRegQueryValue(out, 'MARCEL_HOME'), null)
  assert.equal(parseRegQueryValue('', 'MARCEL_HOME'), null)
  assert.equal(parseRegQueryValue('garbage', 'MARCEL_HOME'), null)
})

// ── expandWindowsEnvRefs ───────────────────────────────────────────────────

test('expandWindowsEnvRefs expands %VAR% case-insensitively', () => {
  assert.equal(expandWindowsEnvRefs('%UserProfile%\\h', { USERPROFILE: 'C:\\Users\\jeff' }), 'C:\\Users\\jeff\\h')
})

test('expandWindowsEnvRefs leaves literal paths and unknown refs intact', () => {
  assert.equal(expandWindowsEnvRefs('F:\\Marcel\\data', {}), 'F:\\Marcel\\data')
  assert.equal(expandWindowsEnvRefs('%NOPE%\\x', {}), '%NOPE%\\x')
})

// ── readWindowsUserEnvVar ──────────────────────────────────────────────────

test('readWindowsUserEnvVar returns null off Windows without spawning', () => {
  let spawned = false

  const exec = () => {
    spawned = true

    return ''
  }

  assert.equal(readWindowsUserEnvVar('MARCEL_HOME', { platform: 'linux', exec }), null)
  assert.equal(spawned, false)
})

test('readWindowsUserEnvVar queries HKCU\\Environment and expands the value', () => {
  const calls = []

  const exec = (cmd, args) => {
    calls.push([cmd, args])

    return 'HKEY_CURRENT_USER\\Environment\r\n    MARCEL_HOME    REG_EXPAND_SZ    %DRIVE%\\Marcel\r\n'
  }

  const value = readWindowsUserEnvVar('MARCEL_HOME', {
    platform: 'win32',
    env: { DRIVE: 'F:' },
    exec
  })

  assert.equal(value, 'F:\\Marcel')
  assert.deepEqual(calls, [['reg', ['query', 'HKCU\\Environment', '/v', 'MARCEL_HOME']]])
})

test('readWindowsUserEnvVar returns null when reg exits non-zero (value missing)', () => {
  const exec = () => {
    throw new Error('reg exited 1')
  }

  assert.equal(readWindowsUserEnvVar('MARCEL_HOME', { platform: 'win32', exec }), null)
})

test('readWindowsUserEnvVar returns null for an empty value', () => {
  const exec = () => '    MARCEL_HOME    REG_SZ    \r\n'
  assert.equal(readWindowsUserEnvVar('MARCEL_HOME', { platform: 'win32', exec }), null)
})
