/**
 * One-time desktop userData cutover. Legacy names are intentionally confined
 * here: this runs before Electron reads any state and keeps encrypted files
 * byte-for-byte (no JSON parsing or re-encryption).
 */
import fs from 'node:fs'
import path from 'node:path'

const RECEIPT = '.marcel-user-data-migration.json'
const LEGACY_DIRS = ['hermes-desktop', 'Hermes']
const REBUILDABLE = /^(?:Cache|Code Cache|GPUCache|DawnCache|Crashpad|Singleton(?:Cookie|Socket))$/i
const EMPTY_SCAFFOLD = new Set(['Preferences', 'Local State'])

function legacyCandidates(): string[] {
  const home = process.env.HOME || process.env.USERPROFILE || ''
  const appData = process.env.APPDATA || (home ? path.join(home, 'AppData', 'Roaming') : '')
  const config = process.env.XDG_CONFIG_HOME || (home ? path.join(home, '.config') : '')
  const mac = home ? path.join(home, 'Library', 'Application Support') : ''

  return [
    ...new Set(
      LEGACY_DIRS.flatMap(name =>
        [appData && path.join(appData, name), config && path.join(config, name), mac && path.join(mac, name)].filter(
          Boolean
        )
      )
    )
  ] as string[]
}

function copyTree(source: string, destination: string): number {
  let count = 0

  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    if (REBUILDABLE.test(entry.name)) {
      continue
    }
    const from = path.join(source, entry.name)
    const to = path.join(destination, entry.name)

    if (entry.isSymbolicLink()) {
      throw new Error(`refusing durable symlink in legacy desktop data: ${entry.name}`)
    }

    if (entry.isDirectory()) {
      fs.mkdirSync(to, { recursive: false })
      count += copyTree(from, to)
    } else if (entry.isFile()) {
      fs.copyFileSync(from, to, fs.constants.COPYFILE_EXCL)
      fs.chmodSync(to, fs.statSync(from).mode & 0o777)
      count++
    }
  }

  return count
}

function emptyScaffold(destination: string): boolean {
  if (!fs.statSync(destination, { throwIfNoEntry: false })?.isDirectory()) {
    return false
  }

  return fs.readdirSync(destination).every(name => {
    const file = path.join(destination, name)

    return EMPTY_SCAFFOLD.has(name) && fs.statSync(file).isFile() && fs.statSync(file).size === 0
  })
}

function migrateOwnedConnectionSchema(stage: string): void {
  for (const name of ['connection.json', 'connections.json']) {
    const file = path.join(stage, name)

    if (!fs.statSync(file, { throwIfNoEntry: false })?.isFile()) {
      continue
    }
    const raw = fs.readFileSync(file, 'utf8')
    // These files contain routing metadata, never credential-store ciphertext.
    // Preserve values exactly; only the Marcel-owned persisted key changes.
    const upgraded = raw.replaceAll('"remoteHermesPath"', '"remoteMarcelPath"')

    if (upgraded !== raw) {
      fs.writeFileSync(file, upgraded, { mode: fs.statSync(file).mode & 0o777 })
    }
  }
}

export function migrateLegacyUserData(destination: string): void {
  if (fs.existsSync(path.join(destination, RECEIPT))) {
    return
  }
  const source = legacyCandidates().find(candidate => fs.statSync(candidate, { throwIfNoEntry: false })?.isDirectory())

  if (!source) {
    return
  }

  if (fs.existsSync(path.join(source, 'SingletonLock'))) {
    throw new Error('Legacy desktop appears to be running; close it before migration.')
  }

  if (fs.existsSync(destination) && !emptyScaffold(destination)) {
    throw new Error(`Marcel desktop data destination already exists: ${destination}`)
  }

  const stage = `${destination}.migration-${process.pid}`

  if (fs.existsSync(stage)) {
    throw new Error(`desktop migration staging path already exists: ${stage}`)
  }
  fs.mkdirSync(stage, { recursive: true, mode: 0o700 })

  try {
    const copied = copyTree(source, stage)
    migrateOwnedConnectionSchema(stage)
    const receipt = { source, destination, copied, rollbackSource: source }
    fs.writeFileSync(path.join(stage, RECEIPT), `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 })
    const fd = fs.openSync(path.join(stage, RECEIPT), 'r')
    fs.fsyncSync(fd)
    fs.closeSync(fd)

    if (fs.existsSync(destination)) {
      fs.rmSync(destination, { recursive: true })
    }
    fs.renameSync(stage, destination)
  } catch (error) {
    fs.rmSync(stage, { recursive: true, force: true })
    throw error
  }
}
