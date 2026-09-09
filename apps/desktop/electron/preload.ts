import { contextBridge, ipcRenderer, webFrame, webUtils } from 'electron'

// Which translucency the OS can back. Asked synchronously because the renderer
// needs it before its first paint, and answered by main because deciding it
// needs `os.release()` — a sandboxed preload may only require electron, events,
// timers and url, so importing node:os here throws before contextBridge runs
// and takes the ENTIRE bridge down with it (window.marcelDesktop undefined =>
// "Desktop IPC bridge is unavailable"). No reply means no glass, which degrades
// to an ordinary opaque window rather than a page thinned over nothing.
const translucencySupport = ipcRenderer.sendSync('marcel:translucency:support')
const hudWindowing = ipcRenderer.sendSync('marcel:hud:windowing')
const hudNativeDrag = hudWindowing?.nativeDrag === true
const launchFlags = ipcRenderer.sendSync('marcel:launch-flags')

contextBridge.exposeInMainWorld('marcelDesktop', {
  glassSupported: translucencySupport?.glass === true,
  translucencySupported: translucencySupport?.translucency === true,
  // Launch-flag fact: the app was started with --local, so the renderer may
  // show the local-models surfaces. Static for the window's lifetime.
  localModelsEnabled: launchFlags?.localModels === true,
  getConnection: profile => ipcRenderer.invoke('marcel:connection', profile),
  // Registry-scoped backend resolution: { connectionId, profile } → descriptor.
  getConnectionFor: payload => ipcRenderer.invoke('marcel:connection:for', payload),
  getProfileRoutes: profiles => ipcRenderer.invoke('marcel:plugin-profile-routes', profiles),
  revalidateConnection: () => ipcRenderer.invoke('marcel:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('marcel:backend:touch', profile),
  getPoolLimits: () => ipcRenderer.invoke('marcel:pool-limits:get'),
  setPoolLimits: limits => ipcRenderer.invoke('marcel:pool-limits:set', limits),
  getGatewayWsUrl: profile => ipcRenderer.invoke('marcel:gateway:ws-url', profile),
  // Registry-scoped fresh WS URL: { connectionId, profile } → result shape of
  // getGatewayWsUrl, minted against that connection's backend.
  getGatewayWsUrlFor: payload => ipcRenderer.invoke('marcel:gateway:ws-url-for', payload),
  // Union agent roster across every registered connection.
  getAgentRoster: () => ipcRenderer.invoke('marcel:agents:roster'),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('marcel:window:openSession', sessionId, opts),
  openSessionInTerminal: (sessionId, opts) => ipcRenderer.invoke('marcel:window:openInTerminal', sessionId, opts),
  openWindow: () => ipcRenderer.invoke('marcel:window:openInstance'),
  openBrowserWindow: tabId => ipcRenderer.invoke('marcel:window:openBrowser', tabId),
  onBrowserPopoutClosed: callback => {
    const listener = (_event, tabId) => callback(tabId)
    ipcRenderer.on('marcel:browser-popout:closed', listener)

    return () => ipcRenderer.removeListener('marcel:browser-popout:closed', listener)
  },
  claimAmbientCue: key => ipcRenderer.invoke('marcel:ambient:claim', key),
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('marcel:wake-indicator:get'),
    setState: state => ipcRenderer.send('marcel:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('marcel:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('marcel:wake-indicator:state', listener)
    }
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('marcel:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('marcel:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('marcel:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('marcel:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('marcel:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('marcel:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('marcel:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('marcel:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('marcel:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  hud: {
    nativeDrag: hudNativeDrag,
    windowing: {
      clientPlacement: hudWindowing?.clientPlacement !== false,
      controlDrag: hudWindowing?.controlDrag === true,
      nativeDrag: hudNativeDrag,
      solid: hudWindowing?.solid === true,
      workspaceTransfer: hudWindowing?.workspaceTransfer === true
    },
    open: request => ipcRenderer.invoke('marcel:hud:open', request),
    close: () => ipcRenderer.invoke('marcel:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('marcel:hud:ignore-mouse', ignore),
    beginMove: () => ipcRenderer.send('marcel:hud:begin-move'),
    endMove: () => ipcRenderer.send('marcel:hud:end-move'),
    moveBy: delta => ipcRenderer.send('marcel:hud:move-by', delta),
    setWorkspaceTransfer: transferring => ipcRenderer.send('marcel:hud:workspace-transfer', transferring),
    setBounds: bounds => ipcRenderer.send('marcel:hud:set-bounds', bounds),
    resetLayout: () => ipcRenderer.invoke('marcel:hud:reset-layout'),
    // Whether the band covers the window below the bar. Main pairs it with the
    // user's translucency setting to decide the native frost (macOS vibrancy /
    // Windows 11 DWM backdrop) — see hudFrostFor.
    setFrost: showing => ipcRenderer.invoke('marcel:hud:frost', showing),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('marcel:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('marcel:hud:goto', listener)

      return () => ipcRenderer.removeListener('marcel:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('marcel:hud:changed', listener)

      return () => ipcRenderer.removeListener('marcel:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('marcel:hud:cursor', listener)

      return () => ipcRenderer.removeListener('marcel:hud:cursor', listener)
    },
    // Main's game-overlay watch: whether a fullscreen app (a game) is under
    // the HUD, so the renderer can step back to the low-opacity overlay
    // treatment while one owns the screen.
    onGameOverlay: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('marcel:hud:game-overlay', listener)

      return () => ipcRenderer.removeListener('marcel:hud:game-overlay', listener)
    }
  },
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('marcel:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('marcel:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('marcel:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('marcel:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('marcel:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('marcel:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('marcel:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('marcel:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('marcel:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('marcel:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('marcel:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('marcel:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('marcel:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('marcel:connection-config:test', payload),
  // Opt-in OS-keychain encryption for stored gateway secrets (default off —
  // see secret-storage-policy.ts). get never touches the OS keychain.
  getSecretStorageEncryption: () => ipcRenderer.invoke('marcel:secret-storage:get'),
  setSecretStorageEncryption: (on: boolean) => ipcRenderer.invoke('marcel:secret-storage:set', on),
  // v2 multi-connection registry: named agent sources (local / remote / cloud / ssh).
  connections: {
    list: () => ipcRenderer.invoke('marcel:connections:list'),
    save: payload => ipcRenderer.invoke('marcel:connections:save', payload),
    remove: id => ipcRenderer.invoke('marcel:connections:remove', id),
    setPrimary: id => ipcRenderer.invoke('marcel:connections:set-primary', id),
    setLaunchMode: mode => ipcRenderer.invoke('marcel:connections:set-launch-mode', mode),
    setLastUsed: id => ipcRenderer.invoke('marcel:connections:set-last-used', id),
    test: id => ipcRenderer.invoke('marcel:connections:test', id),
    updateManaged: id => ipcRenderer.invoke('marcel:connections:update-managed', id),
    // Fan out `marcel update` to every eligible registered connection.
    // Optional excludeIds skips rows the caller updates through another path.
    updateAll: options => ipcRenderer.invoke('marcel:connections:update-all', options),
    // Registry lifecycle push (main → renderer): a connection was removed or
    // materially edited, so secondaries scoped to it must be disposed (and,
    // for edits, re-dialed at the new target).
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:connections:changed', listener)

      return () => ipcRenderer.removeListener('marcel:connections:changed', listener)
    }
  },
  sshConfigHosts: () => ipcRenderer.invoke('marcel:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('marcel:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('marcel:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('marcel:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('marcel:connection-config:oauth-logout', remoteUrl),
  // Marcel Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('marcel:cloud:status'),
    login: () => ipcRenderer.invoke('marcel:cloud:login'),
    logout: () => ipcRenderer.invoke('marcel:cloud:logout'),
    discover: org => ipcRenderer.invoke('marcel:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('marcel:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    get: () => ipcRenderer.invoke('marcel:profile:get'),
    remember: name => ipcRenderer.invoke('marcel:profile:remember', name),
    set: name => ipcRenderer.invoke('marcel:profile:set', name)
  },
  api: request => ipcRenderer.invoke('marcel:api', request),
  notify: payload => ipcRenderer.invoke('marcel:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('marcel:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('marcel:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('marcel:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('marcel:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('marcel:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('marcel:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('marcel:readFileText', filePath),
  readPluginSource: (filePath: string) => ipcRenderer.invoke('marcel:readPluginSource', filePath),
  selectPaths: options => ipcRenderer.invoke('marcel:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('marcel:selectSavePath', options),
  writeClipboard: text => ipcRenderer.invoke('marcel:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('marcel:readClipboard'),
  saveGatewayFile: payload => ipcRenderer.invoke('marcel:saveGatewayFile', payload),
  saveImageFromUrl: url => ipcRenderer.invoke('marcel:saveImageFromUrl', url),
  contextMenuEdit: command => ipcRenderer.invoke('marcel:context-menu:edit', command),
  contextMenuCopyImage: () => ipcRenderer.invoke('marcel:context-menu:copy-image'),
  contextMenuSpellcheck: action => ipcRenderer.invoke('marcel:context-menu:spellcheck', action),
  contextMenuGuestAddWord: payload => ipcRenderer.invoke('marcel:context-menu:guest-add-word', payload),
  onContextMenuSpellcheck: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:context-menu-spellcheck', listener)

    return () => ipcRenderer.removeListener('marcel:context-menu-spellcheck', listener)
  },
  saveImageBuffer: (data, ext, name) => ipcRenderer.invoke('marcel:saveImageBuffer', { data, ext, name }),
  capturePreview: payload => ipcRenderer.invoke('marcel:capturePreview', payload),
  saveClipboardImage: () => ipcRenderer.invoke('marcel:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('marcel:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('marcel:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('marcel:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('marcel:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('marcel:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('marcel:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('marcel:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('marcel:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('marcel:keep-awake', on),
  setDisableF12: blocked => ipcRenderer.send('marcel:devtools:disable-f12', blocked),
  setPreviewShortcutActive: active => ipcRenderer.send('marcel:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('marcel:openExternal', url),
  mcpOauth: {
    // One-shot loopback listener for MCP OAuth against remote backends: bind
    // on this machine, hand redirectUri to mcp.servers.oauth.start, then wait
    // for the provider redirect and relay code/state via oauth.callback.
    listen: () => ipcRenderer.invoke('marcel:mcp-oauth:listen'),
    wait: (id, timeoutMs) => ipcRenderer.invoke('marcel:mcp-oauth:wait', id, timeoutMs),
    cancel: id => ipcRenderer.invoke('marcel:mcp-oauth:cancel', id)
  },
  openPreviewInBrowser: url => ipcRenderer.invoke('marcel:openPreviewInBrowser', url),
  reachPreviewUrl: url => ipcRenderer.invoke('marcel:preview:reach', url),
  setActiveConnectionRoute: route => ipcRenderer.send('marcel:connection:active-route', route),
  fetchLinkTitle: url => ipcRenderer.invoke('marcel:fetchLinkTitle', url),
  resolveFavicon: url => ipcRenderer.invoke('marcel:resolveFavicon', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('marcel:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('marcel:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('marcel:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('marcel:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('marcel:zoom:get'),
    // Synchronous zoom factor (1 = 100%). Coordinate math needs it in the
    // same tick as the event it converts, so no IPC round-trip here.
    factor: () => webFrame.getZoomFactor(),
    setPercent: percent => ipcRenderer.send('marcel:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:zoom:changed', listener)

      return () => ipcRenderer.removeListener('marcel:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('marcel:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('marcel:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('marcel:logs:renderer-error', report),
  readDir: dirPath => ipcRenderer.invoke('marcel:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('marcel:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('marcel:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('marcel:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('marcel:fs:desktopPluginsRoot'),
  logsRoot: () => ipcRenderer.invoke('marcel:fs:logsRoot'),
  agentPluginsRoot: () => ipcRenderer.invoke('marcel:fs:agentPluginsRoot'),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('marcel:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('marcel:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('marcel:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('marcel:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('marcel:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('marcel:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('marcel:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('marcel:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('marcel:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('marcel:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('marcel:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('marcel:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('marcel:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('marcel:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('marcel:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('marcel:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('marcel:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('marcel:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('marcel:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('marcel:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('marcel:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('marcel:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('marcel:git:review:prList', repoPath, branches, numbers),
      fetchPrComment: (repoPath, url) => ipcRenderer.invoke('marcel:git:review:fetchPrComment', repoPath, url),
      createPr: repoPath => ipcRenderer.invoke('marcel:git:review:createPr', repoPath)
    }
  },
  terminal: {
    attach: id => ipcRenderer.invoke('marcel:terminal:attach', id),
    cwd: id => ipcRenderer.invoke('marcel:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('marcel:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('marcel:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('marcel:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('marcel:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `marcel:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `marcel:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('marcel:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('marcel:close-preview-requested', listener)
  },
  onPreviewNav: callback => {
    const listener = (_event, command) => callback(command)
    ipcRenderer.on('marcel:preview-nav', listener)

    return () => ipcRenderer.removeListener('marcel:preview-nav', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('marcel:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('marcel:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('marcel:open-updates', listener)

    return () => ipcRenderer.removeListener('marcel:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:deep-link', listener)

    return () => ipcRenderer.removeListener('marcel:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('marcel:deep-link-ready'),
  probePluginRepo: payload => ipcRenderer.invoke('marcel:plugin:probe', payload),
  installDesktopPlugin: payload => ipcRenderer.invoke('marcel:plugin:installDesktop', payload),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:window-state-changed', listener)

    return () => ipcRenderer.removeListener('marcel:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('marcel:focus-session', listener)

    return () => ipcRenderer.removeListener('marcel:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:notification-action', listener)

    return () => ipcRenderer.removeListener('marcel:notification-action', listener)
  },
  onNotificationActivate: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:notification-activate', listener)

    return () => ipcRenderer.removeListener('marcel:notification-activate', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('marcel:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:backend-exit', listener)

    return () => ipcRenderer.removeListener('marcel:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('marcel:connection:applied', listener)

    return () => ipcRenderer.removeListener('marcel:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('marcel:power-resume', listener)

    return () => ipcRenderer.removeListener('marcel:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('marcel:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('marcel:power-battery', listener)

    return () => ipcRenderer.removeListener('marcel:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:boot-progress', listener)

    return () => ipcRenderer.removeListener('marcel:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('marcel:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('marcel:bootstrap:continue-local'),
  recycleBackend: profile => ipcRenderer.invoke('marcel:backend:recycle', profile),
  resetBootstrap: () => ipcRenderer.invoke('marcel:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('marcel:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('marcel:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('marcel:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('marcel:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('marcel:version'),
  relaunchApp: () => ipcRenderer.invoke('marcel:app:relaunch'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('marcel:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('marcel:uninstall:summary'),
    run: mode => ipcRenderer.invoke('marcel:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('marcel:updates:check'),
    apply: opts => ipcRenderer.invoke('marcel:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('marcel:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('marcel:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('marcel:updates:progress', listener)

      return () => ipcRenderer.removeListener('marcel:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('marcel:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('marcel:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('marcel:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('marcel:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('marcel:found-in-page', listener)

    return () => ipcRenderer.removeListener('marcel:found-in-page', listener)
  },
  // Main-process `before-input-event` forwards Ctrl/Cmd+F here so renderer
  // can open the FindBar even when the GTK compositor has already grabbed
  // the chord at the windowing layer (#81727).
  onOpenFindBarRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('marcel:open-find-bar', listener)

    return () => ipcRenderer.removeListener('marcel:open-find-bar', listener)
  }
})
