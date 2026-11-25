import AVFoundation
import AppKit
import Carbon
import SwiftUI
import UniformTypeIdentifiers
import UserNotifications

final class Host: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
  let s = CompanionState(), sprite = Sprite(), speech = AVSpeechSynthesizer()
  var pendingNotices = [(text: String, thread: String, mood: CardMood)]()
  var lastChatGesture = ""
  var browserActive = false
  var sequenceTimer: Timer?, sequenceID: String?
  var quotaTier: Int?
  var stageReady = false, leased = false, extraMenu = [[String: String]](), lastStagePose = "",
    lastStageAction = ""
  var peersPresent = false, nextPose = 0.0, peers = [String: (NSRect, Double)](),
    lastCollision = [String: Double]()
  let historyEdits = HistoryEdits()
  let card = CardState(), dictation = LocalDictation()
  var hoverKeys: [EventHotKeyRef] = []
  var hoverTimer: Timer?, overPet = false, nextIdleAction = 0.0
  var tempImages = Set<URL>()
  var outsideClicks: Any?, menuKeys: Any?
  let overlay = NSPanel(
    contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered,
    defer: false)
  var chatWindow: NSWindow?, settingsWindow: NSWindow?, bubble: NSPanel?, bubbleThread = ""
  var item: NSStatusItem!, process: Process?, input: FileHandle?, reader: FileHandle?,
    buffer = Data()
  var anim: Timer?, hitTimer: Timer?, flight: Timer?, bubbleTimer: Timer?, overrideUntil = 0.0
  var heartbeatTimer: Timer?, lastHeartbeat = 0.0
  var globalMouse: Any?, localMouse: Any?
  var lastAdvance = 0.0
  var muteHot: EventHotKeyRef?, quitHot: EventHotKeyRef?, syncing = false
  var eventMode: Bool {
    FileManager.default.fileExists(atPath: support.appendingPathComponent("events-only").path)
  }
  var nativeMode: Bool {
    guard let data = try? Data(contentsOf: support.appendingPathComponent("native-account.json")),
      let v = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return false }
    return v["mode"] as? String == "native"
  }
  var hot: EventHotKeyRef?, hotHandler: EventHandlerRef?, currentPack = "", currentShortcut = "",
    ready = false, terminating = false
  var uptime: Double { ProcessInfo.processInfo.systemUptime }
  func applicationDidFinishLaunching(_ note: Notification) {
    if let i = CommandLine.arguments.firstIndex(of: "--profile"),
      i + 1 < CommandLine.arguments.count
    {
      let name = CommandLine.arguments[i + 1]
      if name.range(of: "^[a-zA-Z0-9_-]{1,48}$", options: .regularExpression) != nil {
        s.profile = name
      }
    }
    try? FileManager.default.createDirectory(
      at: s.folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    if let d = try? Data(contentsOf: s.folder.appendingPathComponent("config.json")),
      let cfg = try? JSONDecoder().decode(Config.self, from: d)
    {
      s.config = cfg
    } else if s.packList.contains(s.profile) {
      s.config.pack = s.profile
    }
    overlay.title = "Cartethyia Companion"
    overlay.isOpaque = false
    overlay.backgroundColor = .clear
    overlay.hasShadow = false
    overlay.level = .floating
    overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    overlay.hidesOnDeactivate = false
    sprite.registerForDraggedTypes([.fileURL, .png, .tiff])
    sprite.host = self
    overlay.contentView = sprite
    item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    item.button?.title = "♧"
    item.button?.toolTip = "卡提桌面伙伴"
    UNUserNotificationCenter.current().delegate = self
    s.changed = { [weak self] in self?.apply() }
    apply()
    if !nativeMode && !CommandLine.arguments.contains("--browser-only") {
      overlay.orderFrontRegardless()
      timers(true)
    }
    installPetInputs()
    startBroker()
    menu()
    heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
      guard let self = self, let p = self.process, p.isRunning,
        self.uptime - self.lastHeartbeat > 10
      else { return }
      self.s.status = "idle"
      self.sprite.pose("idle")
      self.clearWorkSurface()
      p.terminate()
    }
    heartbeatTimer?.tolerance = 0.6
    NotificationCenter.default.addObserver(
      forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main
    ) { [weak self] _ in self?.settle() }
    // Finder/Launchpad opens the controls even on a cold launch. Auxiliary profiles start quietly.
    if CommandLine.arguments.count == 1 { settings() }
  }
  func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
    settings()
    return false
  }
  func timers(_ on: Bool) {
    sprite.clipTimer?.invalidate()
    if on { sprite.refreshClipTimer() }
    anim?.invalidate()
    hitTimer?.invalidate()
    if let m = globalMouse {
      NSEvent.removeMonitor(m)
      globalMouse = nil
    }
    if let m = localMouse {
      NSEvent.removeMonitor(m)
      localMouse = nil
    }
    if !on { return }
    anim = Timer.scheduledTimer(withTimeInterval: 0.16, repeats: true) { [weak self] _ in
      guard let self = self else { return }
      self.sharePose()
      if self.stageReady {
        let f = self.overlay.frame
        let pose = "\(Int(f.minX)),\(Int(f.minY))"
        let action = self.sprite.activeClip.map { "clip:" + $0.key } ?? names[self.sprite.row]
        if pose != self.lastStagePose || action != self.lastStageAction {
          self.lastStagePose = pose
          self.lastStageAction = action
          self.send(["op": "display", "pose": pose, "action": action])
        }
      }
      if self.sleeping {
        if self.uptime >= self.overrideUntil {
          if let name = self.sprite.pickClip(self.sprite.clipLibrary?.sleep) {
            _ = self.sprite.playClip(name, loop: true)
          } else {
            self.sprite.pose("waiting")
          }
        }
      } else if !self.leased && self.overrideUntil <= self.uptime {
        self.workPose()
      }
      let step =
        self.sprite.activeClip.map { 1 / $0.fps }
        ?? (self.s.status == "idle" && self.overrideUntil <= self.uptime ? 0.45 : 0.16)
      if self.uptime - self.lastAdvance >= step {
        self.idleLife()
        self.sprite.advance()
        if !self.sprite.held && self.overlay.frame.contains(NSEvent.mouseLocation) {
          self.updateHit(NSEvent.mouseLocation)
        }
        self.lastAdvance = self.uptime
      }
    }
    overlay.acceptsMouseMovedEvents = true
    let track = { [weak self] in
      guard let self = self, !self.sprite.held else { return }
      self.updateHit(NSEvent.mouseLocation)
    }
    globalMouse = NSEvent.addGlobalMonitorForEvents(matching: .mouseMoved) { _ in track() }
    localMouse = NSEvent.addLocalMonitorForEvents(matching: .mouseMoved) { evt in
      track()
      return evt
    }
    do {
      hitTimer = Timer.scheduledTimer(withTimeInterval: 0.14, repeats: true) { _ in track() }
    }
    hitTimer?.tolerance = 0.025
    anim?.tolerance = 0.025
    track()
  }
  func updateHit(_ point: CGPoint) {
    sprite.look(toward: point)
    let ignore = !sprite.hit(point)
    pointer(!ignore && !sprite.held)
    if ignore != overlay.ignoresMouseEvents { overlay.ignoresMouseEvents = ignore }
  }
  func apply() {
    let cfg = s.config
    if !cfg.chat && s.talking { cancel() }
    guard cfg.size.isFinite && cfg.x.isFinite && cfg.y.isFinite else { return }
    if cfg.pack != currentPack {
      if sprite.load(cfg.pack) { currentPack = cfg.pack } else { s.health = "宠物包无法读取：" + cfg.pack }
    }
    if cfg.shortcut != currentShortcut { bindHotkey(cfg.shortcut) }
    let h = max(88, min(288, cfg.size))
    overlay.setContentSize(NSSize(width: h * 192 / 208, height: h))
    if !sprite.held && flight == nil { place(CGPoint(x: cfg.x, y: cfg.y)) }
    if let d = try? JSONEncoder().encode(cfg) {
      try? d.write(to: s.folder.appendingPathComponent("config.json"), options: .atomic)
    }
    sendConfig()
    menu()
  }
  func sendConfig() {
    if let d = try? JSONEncoder().encode(s.config),
      var cfg = try? JSONSerialization.jsonObject(with: d) as? [String: Any]
    {
      if eventMode {
        cfg["chat"] = false
        cfg["whispers"] = false
      }
      cfg["hidden"] = !overlay.isVisible && !browserActive
      if sleeping {
        cfg["whispers"] = false
        cfg["focus"] = true
      }
      send(["op": "config", "config": cfg])
    }
  }
  func menu() {
    guard item != nil else { return }
    let m = NSMenu()
    func add(_ title: String, _ action: Selector) {
      let e = m.addItem(withTitle: title, action: action, keyEquivalent: "")
      e.target = self
    }
    add(overlay.isVisible ? "收起卡提" : "唤醒卡提", #selector(toggle))
    add("和卡提说话", #selector(showChat))
    add("聊天记录", #selector(showHistory))
    add("设置…", #selector(settings))
    add(s.config.muted ? "取消静音" : "静音", #selector(mute))
    add("新建独立伙伴窗口", #selector(extra))
    add(syncing ? "正在切换宠物…" : (nativeMode ? "切回独立伙伴" : "切回 Codex 内置宠物"), #selector(native))
    m.addItem(.separator())
    add("退出", #selector(quit))
    item.menu = m
  }
  func bindHotkey(_ key: String) {
    if let hot = hot { UnregisterEventHotKey(hot) }
    if hotHandler == nil {
      var event = EventTypeSpec(
        eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
      InstallEventHandler(
        GetApplicationEventTarget(),
        { _, event, ptr in
          guard let event = event, let ptr = ptr else { return noErr }
          var id = EventHotKeyID()
          guard
            GetEventParameter(
              event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
              nil, MemoryLayout<EventHotKeyID>.size, nil, &id) == noErr
          else { return noErr }
          let host = Unmanaged<Host>.fromOpaque(ptr).takeUnretainedValue()
          switch id.id {
          case 2: host.mute()
          case 3: host.quit()
          case 10: host.showChat()
          case 11:
            if host.card.mode == .todos && host.bubble?.isVisible == true {
              host.closeCard()
            } else {
              host.showTodos()
            }
          case 12: host.toggleSleep()
          default: host.toggle()
          }
          return noErr
        }, 1, &event, Unmanaged.passUnretained(self).toOpaque(), &hotHandler)
    }
    if s.profile == "main" && muteHot == nil {
      RegisterEventHotKey(
        46, UInt32(controlKey | optionKey | shiftKey), EventHotKeyID(signature: 0x4350_5031, id: 2),
        GetApplicationEventTarget(), 0, &muteHot)
      RegisterEventHotKey(
        12, UInt32(controlKey | optionKey | shiftKey), EventHotKeyID(signature: 0x4350_5031, id: 3),
        GetApplicationEventTarget(), 0, &quitHot)
    }
    let code = ["P": 35, "K": 40, "J": 38][key] ?? 35
    let rc = RegisterEventHotKey(
      UInt32(code), UInt32(controlKey | optionKey), EventHotKeyID(signature: 0x4350_5031, id: 1),
      GetApplicationEventTarget(), 0, &hot)
    currentShortcut = key
    if rc != noErr { s.health = "快捷键已被占用，可在设置中更换" }
  }
  @objc func extra() {
    let alert = NSAlert()
    alert.messageText = "独立伙伴"
    alert.informativeText = "输入一个档案名（英文或数字）。此窗口独立保存角色、设置和对话。"
    let field = NSTextField(string: "companion2")
    alert.accessoryView = field
    field.frame.size = NSSize(width: 220, height: 24)
    alert.addButton(withTitle: "打开")
    alert.addButton(withTitle: "取消")
    if alert.runModal() == .alertFirstButtonReturn,
      field.stringValue.range(of: "^[A-Za-z0-9_-]{1,48}$", options: .regularExpression) != nil
    {
      let p = Process()
      p.executableURL = Bundle.main.executableURL
      p.arguments = ["--profile", field.stringValue]
      try? p.run()
    }
  }
  @objc func native() {
    guard !syncing else { return }
    let consent = support.appendingPathComponent("native-account.json")
    guard FileManager.default.fileExists(atPath: consent.path) else {
      s.health = "可在 Codex 设置中选择宠物；使用安装参数 --sync-native 可启用一键切换。"
      showChat()
      return
    }
    let restore = !nativeMode
    syncing = true
    menu()
    let job = Process()
    job.executableURL = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/pet-python")
    job.arguments = [
      "-B", Bundle.main.resourceURL!.appendingPathComponent("preference.py").path,
      restore ? "restore" : "disable",
    ]
    job.standardOutput = FileHandle.nullDevice
    job.standardError = FileHandle.nullDevice
    job.terminationHandler = { [weak self] job in
      DispatchQueue.main.async {
        guard let self = self else { return }
        self.syncing = false
        if job.terminationStatus == 0 {
          if self.overlay.isVisible == restore { self.toggle() }
          self.s.health = ""
        } else {
          self.s.health = "官方 Pets 未确认切换，可检查 Codex 登录和网络后重试。"
          self.showChat()
        }
        self.menu()
      }
    }
    do { try job.run() } catch {
      syncing = false
      s.health = "未能启动宠物切换服务"
      showChat()
      menu()
    }
  }
  @objc func mute() {
    s.config.muted.toggle()
    if s.config.muted {
      speech.stopSpeaking(at: .immediate)
      bubble?.orderOut(nil)
    }
  }
  @objc func toggle() {
    if overlay.isVisible {
      revokeLease()
      stopFlight()
      dismissHover()
      dictation.cancel()
      overlay.orderOut(nil)
      bubble?.orderOut(nil)
      timers(false)
    } else {
      overlay.orderFrontRegardless()
      timers(true)
    }
    sendConfig()
    menu()
  }
  @objc func quit() { NSApp.terminate(nil) }
  func place(_ p: CGPoint, screenAt point: CGPoint? = nil) {
    let screens = NSScreen.screens
    let probe =
      point ?? CGPoint(x: p.x + overlay.frame.width / 2, y: p.y + overlay.frame.height / 2)
    guard
      let screen = screens.first(where: { $0.frame.contains(probe) })
        ?? screens.min(by: {
          hypot($0.frame.midX - probe.x, $0.frame.midY - probe.y)
            < hypot($1.frame.midX - probe.x, $1.frame.midY - probe.y)
        })
    else { return }
    let f = screen.visibleFrame
    overlay.setFrameOrigin(
      CGPoint(
        x: max(f.minX, min(p.x, f.maxX - overlay.frame.width)),
        y: max(f.minY, min(p.y, f.maxY - overlay.frame.height))))
    anchorCard()
  }
  func settle() {
    stopFlight()
    var p = overlay.frame.origin
    if s.config.snap, let f = overlay.screen?.visibleFrame {
      if abs(p.x - f.minX) < 24 { p.x = f.minX }
      if abs(p.x + overlay.frame.width - f.maxX) < 24 { p.x = f.maxX - overlay.frame.width }
    }
    place(p)
    var cfg = s.config
    cfg.x = overlay.frame.minX
    cfg.y = overlay.frame.minY
    s.config = cfg
  }
  func resetPosition() {
    place(NSEvent.mouseLocation, screenAt: NSEvent.mouseLocation)
    settle()
  }
  func stopFlight() {
    flight?.invalidate()
    flight = nil
  }
  func fling(_ initial: CGVector) {
    stopFlight()
    var v = initial
    var last = uptime
    flight = Timer.scheduledTimer(withTimeInterval: 1 / 60, repeats: true) { [weak self] _ in
      guard let self = self, let current = self.overlay.screen else { return }
      let dt = min(0.035, self.uptime - last)
      last = self.uptime
      v.dy -= (self.s.config.gravity ?? 1400) * dt
      var p = self.overlay.frame.origin
      p.x += v.dx * dt
      p.y += v.dy * dt
      let w = self.overlay.frame.width
      let h = self.overlay.frame.height
      let f = travelArea(
        on: current.visibleFrame, body: self.overlay.frame,
        displays: NSScreen.screens.map(\.visibleFrame), locked: self.s.config.lockScreen == true)
      let bounce = self.s.config.rebound ?? 0.78
      if p.x <= f.minX && v.dx < 0 || p.x + w >= f.maxX && v.dx > 0 {
        v.dx *= -bounce
        self.sprite.bump()
      }
      if p.y + h >= f.maxY { v.dy = -abs(v.dy) * bounce }
      if p.y <= f.minY {
        if abs(v.dy) > 80 { self.sprite.bump() }
        v.dy = abs(v.dy) * bounce
        if v.dy < 36 { v.dy = 0 }
        v.dx *= exp(-(self.s.config.friction ?? 2.5) * dt)
      }
      p.x = min(max(f.minX, p.x), f.maxX - w)
      p.y = min(max(f.minY, p.y), f.maxY - h)
      self.collide(p, &v)
      self.overlay.setFrameOrigin(p)
      self.anchorCard()
      self.sharePose()
      if p.y <= f.minY + 0.5 && abs(v.dx) < 8 && v.dy == 0 { self.settle() }
    }
  }
  func tap() {
    if bubble?.isVisible == true && card.mode == .todos { return }
    if sleeping {
      toggleSleep()
      return
    }
    if let clip = sprite.clipLibrary?.clips.filter({ $0.value.group == "触碰" }).keys.randomElement()
    {
      _ = sprite.playClip(clip)
    } else {
      act("waving")
    }
    if s.config.chat && !eventMode { showChat() } else { sayBubble("我在这里。", thread: "") }
  }
  func workPose() {
    let mapped = s.config.mapping[s.status] ?? "idle"
    let stories = [
      "thinking": "思考时冒出气泡", "working": "认真敲动按键", "review": "把完成的记录归档",
      "waiting-for-approval": "等你点头时踱步", "success": "收好剑鞘庆祝", "error": "垂下眼睛轻轻叹气",
    ]
    if mapped == standardMap[s.status], let key = stories[s.status],
      sprite.clipLibrary?.clips[key] != nil
    {
      if sprite.activeClip?.key == key { return }
      sprite.pose(mapped)
      _ = sprite.playClip(key, loop: true)
    } else {
      sprite.pose(mapped)
    }
  }
  func act(_ name: String) {
    guard names.contains(name) else { return }
    sprite.pose(name)
    overrideUntil = uptime + 0.8
  }
  func window<V: View>(_ title: String, _ view: V) -> NSWindow {
    let w = NSWindow(contentViewController: NSHostingController(rootView: view))
    w.title = title
    w.isReleasedWhenClosed = false
    w.styleMask = [.titled, .closable, .resizable]
    w.center()
    return w
  }
  @objc func settings() {
    if settingsWindow == nil { settingsWindow = window("卡提 · 设置", Settings(state: s, host: self)) }
    present(settingsWindow)
  }
  @objc func showChat() {
    guard !sleeping, s.config.chat, !eventMode else { return }
    if !overlay.isVisible { toggle() }
    if s.talking {
      showSpoken(s.partial.isEmpty ? "…" : s.partial, duration: 0)
      return
    }
    bubbleTimer?.invalidate()
    card.speaker = "Cartethyia"
    card.note = ""
    surface(.compose, focus: true)
  }
  @objc func showHistory() {
    if chatWindow == nil {
      chatWindow = window("卡提 · 聊天记录", ChatView(state: s, host: self, edits: historyEdits))
    }
    present(chatWindow)
  }
  func present(_ w: NSWindow?) {
    NSApp.activate(ignoringOtherApps: true)
    if w?.isMiniaturized == true { w?.deminiaturize(nil) }
    w?.makeKeyAndOrderFront(nil)
  }
  func attachImage() {
    let panel = NSOpenPanel()
    panel.allowedContentTypes = [.png, .jpeg]
    panel.allowsMultipleSelection = false
    if panel.runModal() == .OK {
      s.attachment = panel.url
      showChat()
    }
  }
  func ask(_ text: String) {
    guard !s.talking, s.config.chat, !eventMode else { return }
    s.partial = "…"
    s.talking = true
    dictation.cancel()
    bubble?.orderOut(nil)
    card.variant = (card.variant + Int.random(in: 1...5)) % 24
    showSpoken("…", duration: 0, mood: .curious)
    var msg: [String: Any] = ["op": "chat", "text": text]
    if let url = s.attachment {
      msg["image"] = url.path
      s.attachment = nil
    }
    send(msg)
  }
  func cancel() {
    send(["op": "cancel"])
    s.talking = false
    s.partial = ""
  }
  func clearChat() {
    cancel()
    s.pairs = []
    send(["op": "clear"])
  }
  func send(_ obj: [String: Any]) {
    guard let input = input, let data = try? JSONSerialization.data(withJSONObject: obj) else {
      return
    }
    try? input.write(contentsOf: data + Data([10]))
  }
  func startBroker() {
    let p = Process()
    let out = Pipe()
    let inp = Pipe()
    p.executableURL = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/pet-python")
    p.arguments = [
      "-B", "-u", Bundle.main.resourceURL!.appendingPathComponent("broker.py").path, s.profile,
    ]
    p.standardOutput = out
    p.standardInput = inp
    p.standardError = FileHandle.nullDevice
    let handle = out.fileHandleForReading
    handle.readabilityHandler = { [weak self] h in
      let data = h.availableData
      if data.isEmpty {
        h.readabilityHandler = nil
        return
      }
      DispatchQueue.main.async { self?.receive(data) }
    }
    p.terminationHandler = { [weak self] p in
      DispatchQueue.main.async {
        guard let self = self, !self.terminating else { return }
        self.input = nil
        self.sprite.pose("idle")
        self.s.status = "idle"
        self.s.talking = false
        self.s.partial = ""
        self.clearWorkSurface()
        self.s.health = "本地事件服务已断开"
        if p.terminationStatus == 3 {
          NSApp.terminate(nil)
        } else {
          DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.startBroker() }
        }
      }
    }
    do {
      try p.run()
      lastHeartbeat = uptime
      process = p
      reader = handle
      input = inp.fileHandleForWriting
      sendConfig()
      if CommandLine.arguments.contains("--api") || CommandLine.arguments.contains("--browser-only")
      {
        send(["op": "web-open", "open": CommandLine.arguments.contains("--browser-only")])
      }
    } catch { s.health = "无法启动本地服务" }
  }
  func clearWorkSurface() {
    overrideUntil = 0
    s.tool = ""
    s.progress = ""
    s.thread = ""
    s.since = 0
    if card.mode == .work || card.mode == .hover || s.talking { bubble?.orderOut(nil) }
    if overlay.isVisible && overPet && !sleeping { surface(.hover) }
  }
  func receive(_ data: Data) {
    buffer.append(data)
    while let i = buffer.firstIndex(of: 10) {
      let line = buffer.prefix(upTo: i)
      let m = (try? JSONSerialization.jsonObject(with: line)) as? [String: Any]
      buffer.removeSubrange(...i)
      if let m = m { handle(m) }
    }
  }
  func handle(_ m: [String: Any]) {
    let text = m["text"] as? String ?? ""
    let thread = m["thread"] as? String ?? ""
    switch m["type"] as? String {
    case "web-presence":
      browserActive = m["active"] as? Bool == true
      sendConfig()
    case "web-url":
      if let u = (m["url"] as? String).flatMap(URL.init(string:)), u.scheme == "http",
        u.host == "127.0.0.1"
      {
        stageReady = true
        if m["open"] as? Bool != false { NSWorkspace.shared.open(u) }
      }
    case "external": if let cmd = m["command"] as? [String: Any] { external(cmd) }
    case "peer-count":
      peersPresent = (m["peers"] as? Bool) == true
      nextPose = 0
      sharePose()
    case "peer": peerEvent(m)
    case "heartbeat":
      lastHeartbeat = uptime
    case "history":
      s.health = ""
      if let data = m["pairs"], let raw = try? JSONSerialization.data(withJSONObject: data),
        let items = try? JSONDecoder().decode([ChatPair].self, from: raw)
      {
        s.pairs = items
      }
    case "status":
      s.status = m["state"] as? String ?? "idle"
      s.thread = thread
      s.tool = m["tool"] as? String ?? ""
      s.progress = m["progress"] as? String ?? ""
      s.since = m["since"] as? Double ?? 0
      if !sleeping && !leased {
        overrideUntil = 0
        workPose()
        if hoverMayAppear && overlay.isVisible {
          if overPet {
            surface(.hover)
          } else if s.status != "idle" {
            surface(.work)
          } else {
            bubble?.orderOut(nil)
          }
        }
      }
    case "partial":
      s.partial = text
      if !sleeping { showSpoken(text, duration: 0, mood: .curious) }
    case "failure":
      s.partial = text
      s.talking = false
      if !sleeping { showSpoken(text, title: "本地对话", duration: 12, mood: .sad) }
    case "reply", "whisper":
      let whisper = (m["type"] as? String == "whisper")
      if sleeping { return }
      s.emotion = m["emotion"] as? String ?? ""
      let action = m["action"] as? String ?? "idle"
      let mood = CardMood(emotion: s.emotion, action: action)
      if !leased && s.status == "idle" && (!whisper || !s.config.muted) {
        let choices = mood.gestures.filter { $0 != lastChatGesture && sprite.clipLibrary?.clips[$0] != nil }
        if let key = choices.randomElement(), sprite.playClip(key) { lastChatGesture = key }
        else { act(action) }
      }
      if whisper {
        if !s.config.muted && !leased {
          sayBubble(text, thread: "", mood: mood)
          speak(
            text, m["manual"] as? Bool == true ? s.config.voiceChat == true : s.config.voiceWhisper)
        }
      } else {
        s.partial = ""
        s.talking = false
        showSpoken(
          text, duration: max(9, min(40, Double(text.count) * 0.22)),
          art: s.config.replyArt == true ? s.pairs.last : nil, mood: mood)
        speak(text, s.config.voiceChat == true)
      }
    case "archive-entry":
      if let pair = m["pair"], let raw = try? JSONSerialization.data(withJSONObject: pair),
        let entry = try? JSONDecoder().decode(ChatPair.self, from: raw)
      {
        s.pairs.append(entry)
      }
    case "notice":
      let state = m["state"] as? String ?? ""
      let message = titles[state] ?? state
      if !sleeping && !leased && s.config.notifications && !s.config.muted {
        sayBubble(message, thread: thread, mood: CardMood(status: state))
        notify(message, thread)
        speak(message, s.config.voiceNotice)
      }
    case "task-list":
      if let obj = m["items"], let bytes = try? JSONSerialization.data(withJSONObject: obj),
        let t = try? JSONDecoder().decode([PetTask].self, from: bytes)
      {
        s.tasks = t
      }
    case "ui-error":
      card.note = text
      s.health = text
    case "manual-weather": if !sleeping { showSpoken(text, title: "天气") }
    case "dream": if sleeping { showSpoken(text, title: "梦话", duration: 7) }
    case "weather": s.weather = text
    case "quota":
      s.quota = text
      if let used = m["used"] as? Double {
        let t = min(5, max(0, Int(used / 20)))
        if t != quotaTier && quotaTier != nil && s.config.automaticQuota == true && !leased
          && !sleeping && !s.config.muted
        {
          sprite.playScene(PetScene.allCases.filter { $0.group == "额度" }[t])
          showSpoken(text, title: "Codex 额度")
        }
        quotaTier = t
      }
    case "todo":
      if !sleeping && !leased && !s.config.muted {
        sayBubble(text, thread: thread)
        speak(text, s.config.voiceTodo)
        if m["completed"] as? Bool == true { act("jumping") }
      }
    default: break
    }
  }
  func speak(_ text: String, _ enabled: Bool, manual: Bool = false) {
    if enabled && (manual || !s.config.muted) {
      let u = AVSpeechUtterance(string: text)
      u.voice =
        s.config.voiceName.flatMap { AVSpeechSynthesisVoice(identifier: $0) }
        ?? AVSpeechSynthesisVoice(language: "zh-CN")
      u.volume = Float(s.config.volume)
      speech.speak(u)
    }
  }
  func sayBubble(_ text: String, thread: String, mood: CardMood = .calm) {
    if s.talking || (bubble?.isVisible == true && (card.mode == .compose || card.mode == .todos)) {
      pendingNotices.removeAll { $0.text == text && $0.thread == thread }
      if pendingNotices.count >= 4 { pendingNotices.removeFirst() }
      pendingNotices.append((text, thread, mood))
      return
    }
    showSpoken(text, target: thread, duration: 10, mood: mood)
  }
  @objc func bubbleClick() {
    if bubbleThread.isEmpty { showChat() } else { openThread(bubbleThread) }
    bubble?.orderOut(nil)
  }
  func openThread(_ id: String) {
    if UUID(uuidString: id) != nil, let u = URL(string: "codex://threads/" + id) {
      NSWorkspace.shared.open(u)
    }
  }
  func requestNotifications() {
    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
  }
  func notify(_ text: String, _ id: String) {
    let c = UNMutableNotificationContent()
    c.title = "Cartethyia"
    c.body = text
    c.userInfo = ["thread": id]
    if s.config.sound { c.sound = .default }
    UNUserNotificationCenter.current().add(
      UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil))
  }
  func userNotificationCenter(
    _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
    withCompletionHandler done: @escaping () -> Void
  ) {
    if let id = response.notification.request.content.userInfo["thread"] as? String {
      DispatchQueue.main.async { self.openThread(id) }
    }
    done()
  }
  func applicationWillTerminate(_ n: Notification) {
    terminating = true
    dictation.cancel()
    for u in tempImages { try? FileManager.default.removeItem(at: u) }
    if let m = outsideClicks { NSEvent.removeMonitor(m) }
    if let m = menuKeys { NSEvent.removeMonitor(m) }
    heartbeatTimer?.invalidate()
    try? input?.close()
    reader?.readabilityHandler = nil
    stopFlight()
    timers(false)
  }
}
