import { spawn } from 'node:child_process'

export interface LaunchResult {
  code: null | number
  error?: string
}

const resolveMarcelBin = () => process.env.MARCEL_BIN?.trim() || 'marcel'

export const launchMarcelCommand = (args: string[]): Promise<LaunchResult> =>
  new Promise(resolve => {
    const child = spawn(resolveMarcelBin(), args, { stdio: 'inherit' })

    child.on('error', err => resolve({ code: null, error: err.message }))
    child.on('exit', code => resolve({ code }))
  })
