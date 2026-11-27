import AppKit
import Carbon
import SwiftUI

struct PetTask: Codable, Identifiable {
  let id: String, text: String, due: Double?, done: Bool
}
enum PetCard { case details, work, speech, compose, todos, usage }
final class CardPanel: NSPanel {
  override var canBecomeKey: Bool { true }
  override var canBecomeMain: Bool { false }
}
final class CardState: ObservableObject {
  @Published var picture = ""
  @Published var mood = CardMood.calm
  @Published var variant = 0
  @Published var tipAtTop = false
  @Published var tipX: CGFloat = 120
  @Published var mode = PetCard.details
  @Published var message = ""
  @Published var speaker = "Cartethyia"
  @Published var target = ""
  @Published var art: ChatPair?
  @Published var recording = false
  @Published var note = ""
  @Published var todoText = ""
  @Published var deadline = Date().addingTimeInterval(3600)
  @Published var dated = false
  @Published var confirmDelete: String?
}
struct PetCardView: View {
  @ObservedObject var state: CompanionState
  @ObservedObject var card: CardState
  let host: Host
  func icon(_ label: String, _ symbol: String, _ action: @escaping () -> Void) -> some View {
    Button(action: action) { Image(systemName: symbol).frame(width: 21, height: 20) }.buttonStyle(
      .plain
    ).foregroundStyle(cardPine).accessibilityLabel(label).help(label)
  }
  var details: some View {
    VStack(alignment: .leading, spacing: 3) {
      Text("工具　" + (state.tool.isEmpty ? "—" : state.tool))
      TimelineView(.periodic(from: .now, by: 1)) { t in
        Text(
          "耗时　"
            + (state.since > 0 ? "\(max(0,Int(t.date.timeIntervalSince1970-state.since))) 秒" : "—"))
      }
      Text("计划　" + (state.progress.isEmpty ? "暂无计划进度" : state.progress)).lineLimit(2)
    }.font(.custom("STYuanti-SC-Regular", fixedSize: 12))
  }
  var body: some View {
    let detail = card.mode == .details || card.mode == .work
    let mood = detail ? CardMood(status: state.status) : card.mood
    let shape = PaperBubble(tipAtTop: card.tipAtTop, tipX: card.tipX)
    VStack(alignment: .leading, spacing: 6) {
      if detail {
        HStack(spacing: 11) {
          CardPortrait(sprite: host.sprite, mood: mood, variant: card.variant)
            .frame(width: 65, height: card.mode == .work ? 61 : 76)
          VStack(alignment: .leading, spacing: 5) {
            Text(titles[state.status] ?? state.status).font(PetLettering.title(17))
            if card.mode == .details { details }
            else {
              let content = [state.tool, state.progress].filter { !$0.isEmpty }.joined(separator: " · ")
              Text(content.isEmpty ? (state.status == "thinking" ? "让我想一想。" : "我在跟进这个回合。") : content)
                .font(.system(size: 12, design: .rounded)).lineLimit(2)
            }
          }
          Spacer()
          icon("收起", "xmark") { host.closeCard() }
        }
      } else {
        HStack {
          Text(card.mode == .todos ? "待办事项" : card.mode == .usage ? "当前任务用量" : card.speaker)
            .font(card.speaker == "Cartethyia" && card.mode != .todos
                  ? .system(size: 13, weight: .semibold, design: .serif).italic() : PetLettering.title(14))
          Spacer()
          if card.mode == .compose { icon("聊天记录", "clock.arrow.circlepath") { host.showHistory() } }
          icon("收起", "xmark") { host.closeCard() }
        }.foregroundStyle(cardPine)
      }
      switch card.mode {
      case .details, .work: EmptyView()
      case .speech:
        if let picture = state.pictures.first(where: { $0.id == card.picture }),
          let image = picture.thumbnail(size: 160) {
          Image(nsImage: image).resizable().scaledToFit().frame(maxWidth: .infinity)
            .frame(height: 111).accessibilityLabel(picture.title)
        }
        ScrollView {
          Text(card.message).font(PetLettering.title(17)).lineSpacing(3)
            .multilineTextAlignment(card.message.count < 45 ? .center : .leading)
            .textSelection(.enabled).frame(maxWidth: .infinity)
        }
        if card.picture.isEmpty, let art = card.art { PairArt(pair: art, host: host) }
        HStack {
          if state.talking { Button("中断") { host.cancel(); host.closeCard() } }
          else if !card.target.isEmpty { Button("打开对应会话") { host.openThread(card.target) } }
          else { Button("回复") { host.showChat() } }
          Spacer()
          if !state.talking && !card.message.isEmpty {
            icon("朗读这句话", "speaker.wave.2") { host.readAloud(card.message) }
          }
        }.buttonStyle(.plain).font(PetLettering.title(13)).foregroundStyle(cardPine)
      case .usage:
        if !state.usageChoices.isEmpty {
          Picker("主回合", selection: Binding(get: { state.usageSelected }, set: { value in
            state.usageSelected = value
            host.send(["op":"usage","selected":value])
          })) {
            ForEach(state.usageChoices, id: \.key) { Text($0.label).tag($0.key) }
          }
        }
        ScrollView { Text(state.usage).font(.system(size:13)).textSelection(.enabled)
          .frame(maxWidth:.infinity, alignment:.leading) }
        Button("刷新账户数据") { host.send(["op":"usage", "selected":state.usageSelected]) }
      case .compose:
        HStack(spacing: 8) {
          CardPortrait(sprite: host.sprite, mood: .curious, variant: card.variant).frame(width: 48,height: 46)
          PetInput(text: $state.draft, submit: submit).frame(height: 28)
        }
        if let url = state.attachment {
          HStack {
            Text(url.lastPathComponent).font(.caption).lineLimit(1)
            icon("移除附件", "xmark.circle") { state.attachment = nil }
          }
        }
        if !card.note.isEmpty { Text(card.note).font(.caption) }
        HStack {
          icon("选择图片", "photo") { host.attachImage() }.disabled(!state.visionAvailable)
          icon("粘贴图片", "clipboard") { _ = host.attachPasteboard(.general) }.disabled(!state.visionAvailable)
          icon("截取区域", "viewfinder") { host.captureRegion() }.disabled(!state.visionAvailable)
          Image(systemName: card.recording ? "waveform.circle.fill" : "mic").frame(width:25,height:22)
            .foregroundStyle(cardPine).gesture(DragGesture(minimumDistance: 0)
              .onChanged { _ in host.dictation.start(host) }.onEnded { _ in host.dictation.release() })
            .help("按住说话，松开转文字")
          Spacer()
          Button("发送", action: submit).font(PetLettering.title(14)).disabled(
            state.talking || (state.draft.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && state.attachment == nil))
        }
      case .todos:
        ScrollView {
          VStack(alignment: .leading, spacing: 6) {
            ForEach(state.tasks) { item in
              HStack {
                icon(item.done ? "重新打开" : "完成", item.done ? "checkmark.circle.fill" : "circle") {
                  host.send(["op": "todo-toggle", "id": item.id])
                }
                VStack(alignment: .leading) {
                  Text(item.text).strikethrough(item.done)
                  if let due = item.due {
                    Text(Date(timeIntervalSince1970: due), style: .relative).font(.caption)
                  }
                }
                Spacer()
                icon("删除待办", card.confirmDelete == item.id ? "trash.fill" : "trash") {
                  if card.confirmDelete == item.id {
                    host.send(["op": "todo-delete", "id": item.id])
                    card.confirmDelete = nil
                  } else {
                    card.confirmDelete = item.id
                  }
                }
              }
            }
          }
        }.font(.system(size: 12))
        TextField("添加待办", text: $card.todoText).onSubmit(addTodo)
        HStack {
          Toggle("到期", isOn: $card.dated)
          if card.dated {
            DatePicker(
              "", selection: $card.deadline, in: Date()...,
              displayedComponents: [.date, .hourAndMinute]
            ).labelsHidden()
          }
          Spacer()
          Button("添加", action: addTodo).disabled(
            card.todoText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
      }
    }.padding(.horizontal,14).padding(.vertical,10)
    .padding(card.tipAtTop ? .top : .bottom, 10)
    .foregroundStyle(cardInk).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(shape.fill(paper)).overlay(shape.stroke(cardPine.opacity(0.26),lineWidth: 1))
    .padding(2).environment(\.colorScheme, .light)
    .onExitCommand { host.closeCard() }
  }
  func submit() {
    let text = state.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty || state.attachment != nil else { return }
    state.draft = ""
    host.ask(text.isEmpty ? "请描述这张图。" : text)
  }
  func addTodo() {
    let text = card.todoText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    var cmd: [String: Any] = ["op": "todo-add", "text": text]
    if card.dated { cmd["due"] = ISO8601DateFormatter().string(from: card.deadline) }
    host.send(cmd)
    card.todoText = ""
  }
}
extension Host {
  var sleeping: Bool { s.config.asleep == true }
  func refreshHoverKeys() {
    for key in hoverKeys { UnregisterEventHotKey(key) }
    hoverKeys.removeAll()
    guard overPet, overlay.isVisible, !sprite.held,
      !(bubble?.isVisible == true
        && (card.mode == .compose
          || (card.mode == .todos && bubble?.firstResponder is NSTextView))),
      settingsWindow?.isKeyWindow != true,
      chatWindow?.isKeyWindow != true
    else { return }
    for (code, id) in [(kVK_ANSI_T, 10), (kVK_ANSI_D, 11), (kVK_ANSI_S, 12)] {
      var key: EventHotKeyRef?
      if RegisterEventHotKey(
        UInt32(code), 0, EventHotKeyID(signature: 0x4350_5031, id: UInt32(id)),
        GetApplicationEventTarget(), 0, &key) == noErr, let ref = key
      {
        hoverKeys.append(ref)
      }
    }
  }
  func surface(_ mode: PetCard, focus: Bool = false) {
    guard overlay.isVisible else { return }
    let same = bubble?.isVisible == true && card.mode == mode
    if card.mode == .usage && mode != .usage { send(["op":"usage-close"]) }
    card.mode = mode
    if bubble == nil {
      let p = CardPanel(
        contentRect: .zero, styleMask: [.borderless], backing: .buffered, defer: false)
      p.isOpaque = false
      p.backgroundColor = .clear
      p.hasShadow = true
      p.level = .floating
      p.collectionBehavior = overlay.collectionBehavior
      p.hidesOnDeactivate = false
      p.isReleasedWhenClosed = false
      p.contentView = NSHostingView(rootView: PetCardView(state: s, card: card, host: self))
      bubble = p
    }
    guard let panel = bubble else { return }
    let desired: NSSize
    switch mode {
    case .details: desired = NSSize(width: 288, height: 122)
    case .work: desired = NSSize(width: 241, height: 97)
    case .compose:
      desired = NSSize(width: 312, height: s.attachment != nil || !card.note.isEmpty ? 186 : 148)
    case .todos: desired = NSSize(width: 345, height: 266)
    case .usage: desired = NSSize(width: 366, height: 310)
    case .speech:
      desired = NSSize(
        width: 273,
        height: min(
          440,
          124 + CGFloat(card.message.count / 14) * 22 + (card.picture.isEmpty ? (card.art == nil ? 0 : 58) : 111)))
    }
    if panel.frame.size != desired { panel.setContentSize(desired) }
    panel.title =
      mode == .details
      ? "卡提 · 工作详情" : mode == .compose ? "卡提 · 输入" : mode == .todos ? "卡提 · 待办" : "卡提 · 气泡"
    panel.ignoresMouseEvents = false
    if panel.parent !== overlay { overlay.addChildWindow(panel, ordered: .above) }
    anchorCard()
    if !same { panel.orderFrontRegardless() }
    if focus {
      NSApp.activate(ignoringOtherApps: true)
      panel.makeKeyAndOrderFront(nil)
      panel.makeKey()
    }
    if !same { refreshHoverKeys() }
  }
  func anchorCard() {
    guard let panel = bubble, let screen = overlay.screen else { return }
    let area = screen.visibleFrame
    let pet = overlay.frame
    let size = panel.frame.size
    let above = pet.maxY - 4
    let below = pet.minY - size.height + 3
    let y =
      above + size.height <= area.maxY
      ? above : below >= area.minY ? below : min(area.maxY - size.height, max(area.minY, above))
    let pos = NSPoint(
      x: min(area.maxX - size.width, max(area.minX, pet.midX - size.width / 2)), y: y)
    let top = y < pet.minY
    let tip = min(size.width - 26, max(26, pet.midX - pos.x - 2))
    if card.tipAtTop != top { card.tipAtTop = top }
    if abs(card.tipX-tip) > 0.5 { card.tipX = tip }
    if abs(panel.frame.minX - pos.x) > 0.5 || abs(panel.frame.minY - pos.y) > 0.5 {
      panel.setFrameOrigin(pos)
    }
  }
  func closeCard() {
    if stageReady { send(["op": "display", "bubble": ""]) }
    if card.mode == .usage { send(["op":"usage-close"]) }
    dictation.cancel()
    bubbleTimer?.invalidate()
    bubble?.orderOut(nil)
    pendingNotices.removeAll { $0.expires < uptime }
    if !sleeping && !s.config.muted && !s.talking && overlay.isVisible && !pendingNotices.isEmpty {
      let n = pendingNotices.removeFirst()
      shownNotice = (n.thread, n.turn)
      showSpoken(n.text, target: n.thread, duration: 10, mood: n.mood, picture: n.picture)
    } else { shownNotice = nil }
  }
  func dismissHover() {
    overPet = false
    refreshHoverKeys()
  }
  func pointer(_ hit: Bool) {
    guard overPet != hit else { return }
    overPet = hit
    refreshHoverKeys()
  }
  func showSpoken(
    _ text: String, title: String = "Cartethyia", target: String = "", duration: Double = 9,
    art: ChatPair? = nil, mood: CardMood = .calm, picture: String = ""
  ) {
    if stageReady { send(["op": "display", "bubble": text, "duration": duration, "mood": mood.rawValue, "variant": card.variant, "picture": picture]) }
    guard overlay.isVisible else { return }
    bubbleTimer?.invalidate()
    if bubble?.isVisible == true && (card.mode == .todos || card.mode == .compose || card.mode == .usage) { return }
    if card.mood != mood { card.mood = mood }
    card.picture = picture
    card.art = art
    card.message = text
    card.speaker = title
    card.target = target
    surface(.speech)
    if duration > 0 {
      bubbleTimer = Timer.scheduledTimer(withTimeInterval: duration, repeats: false) {
        [weak self] _ in
        guard let self = self, self.card.mode == .speech else { return }
        if self.speech.isSpeaking {
          self.waitForVoice()
        } else {
          self.closeCard()
        }
      }
    }
  }
  func waitForVoice() {
    bubbleTimer = Timer.scheduledTimer(withTimeInterval: 0.6, repeats: false) { [weak self] _ in
      guard let self = self, self.card.mode == .speech else { return }
      if self.speech.isSpeaking { self.waitForVoice() } else { self.closeCard() }
    }
  }
  func petMenu() -> NSMenu {
    let m = NSMenu()
    @discardableResult func add(_ title: String, _ cmd: String, _ parent: NSMenu? = nil, _ enabled: Bool = true) -> NSMenuItem {
      let i = NSMenuItem(title: title, action: #selector(petCommand(_:)), keyEquivalent: "")
      i.target = self
      i.representedObject = cmd
      i.isEnabled = enabled
      (parent ?? m).addItem(i)
      return i
    }
    m.autoenablesItems = false
    add(sleeping ? "叫醒卡提" : "睡觉", "sleep")
    add("和卡提说话　T", "chat", nil, !sleeping && s.config.chat && chatModelReady)
    add("说句碎碎念", "whisper", nil, !sleeping && whisperModelReady)
    add("待办事项　D", "todos", nil, !sleeping)
    add("工作详情", "details", nil, !sleeping)
    add("账户额度", "quota", nil, !sleeping)
    add("当前任务用量", "usage", nil, !sleeping)
    let gallery = NSMenu()
    m.addItem(withTitle: "配图", action: nil, keyEquivalent: "").submenu = gallery
    let caption = add(s.config.replyArt == true ? "可用于对话与碎碎念" : "手动点选配图", "", gallery, false)
    caption.isEnabled = false
    gallery.autoenablesItems = false
    for picture in s.pictures {
      let item = add(picture.title, "picture:" + picture.id, gallery, !sleeping && whisperModelReady)
      item.image = picture.thumbnail(size: 40)
      item.toolTip = picture.description
    }
    add("查询天气", "weather", nil, !sleeping)
    let actions = NSMenu()
    let slot = m.addItem(withTitle: "点播动作", action: nil, keyEquivalent: "")
    slot.submenu = actions
    slot.isEnabled = !sleeping
    if let clips = sprite.clipLibrary?.clips, !clips.isEmpty {
      let sub = actions
      for (group, keys) in Dictionary(grouping: clips.keys, by: { clips[$0]?.group ?? "" }).sorted(
        by: { $0.key < $1.key })
      {
        let branch: NSMenu
        if group.isEmpty {
          branch = sub
        } else {
          branch = NSMenu()
          sub.addItem(withTitle: group, action: nil, keyEquivalent: "").submenu = branch
        }
        for key in keys.sorted() { add(key, "clip:" + key, branch) }
      }
    }
    if sprite.clipLibrary?.clips.isEmpty != false {
      for trick in PetTrick.allCases { add(trick.rawValue, "trick:" + trick.rawValue, actions) }
      for scene in PetScene.allCases { add(scene.rawValue, "scene:" + scene.rawValue, actions) }
    }
    m.addItem(.separator())
    add(s.config.roaming == true ? "停止漫游" : "开始漫游", "roam")
    add("回到屏幕中间", "home")
    add("聊天记录", "history")
    add("打开 Codex", "codex")
    add("浏览器舞台与本地接口", "web")
    if !extraMenu.isEmpty {
      let submenu = NSMenu()
      m.addItem(withTitle: "更多", action: nil, keyEquivalent: "").submenu = submenu
      for e in extraMenu {
        if let title = e["label"], let id = e["id"] { add(title, "custom:" + id, submenu) }
      }
    }
    add("设置…", "settings")
    add("重载配置", "reload")
    add("收起", "hide")
    return m
  }
  @objc func petCommand(_ sender: NSMenuItem) {
    guard let cmd = sender.representedObject as? String else { return }
    if cmd.hasPrefix("custom:") {
      send(["op": "web-event", "id": String(cmd.dropFirst(7))])
      return
    }
    if cmd.hasPrefix("picture:"), !sleeping {
      closeCard()
      send(["op":"whisper", "picture":String(cmd.dropFirst(8))])
      return
    }
    if cmd.hasPrefix("clip:"), !sleeping {
      _ = performClip(String(cmd.dropFirst(5)), speak: true)
      return
    }
    if cmd.hasPrefix("scene:"), let scene = PetScene(rawValue: String(cmd.dropFirst(6))), !sleeping
    {
      sprite.playScene(scene)
      return
    }
    if cmd.hasPrefix("trick:"), let t = PetTrick(rawValue: String(cmd.dropFirst(6))), !sleeping {
      sprite.play(t)
      return
    }
    switch cmd {
    case "web": send(["op": "web-open"])
    case "chat": showChat()
    case "details":
      bubbleTimer?.invalidate()
      surface(.details)
    case "todos": showTodos()
    case "whisper":
      if !sleeping {
        closeCard()
        showSpoken("让我想想…", duration: 4)
        send(["op": "whisper"])
      }
    case "quota":
      closeCard()
      showSpoken(s.quota.isEmpty ? "正在读取账户额度…" : s.quota, title: "Codex 账户额度", duration: 18)
      send(["op":"quota-read"])
    case "usage":
      closeCard()
      s.usage = "正在读取本机回合记录…"
      surface(.usage, focus: true)
      send(["op":"usage", "selected":""])
    case "weather":
      if s.config.weatherEnabled == true && !(s.config.weatherCity ?? "").isEmpty {
        send(["op": "weather"])
      } else {
        showSpoken("请先在「设置 → 环境」填写城市并开启天气。", title: "天气")
      }
    case "sleep": toggleSleep()
    case "home":
      if let f = (overlay.screen ?? NSScreen.main)?.visibleFrame {
        stopFlight()
        place(CGPoint(x: f.midX - overlay.frame.width / 2, y: f.midY - overlay.frame.height / 2))
        settle()
      }
    case "roam": s.config.roaming = !(s.config.roaming ?? false)
    case "history": showHistory()
    case "settings": settings()
    case "hide": toggle()
    case "codex":
      if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.openai.codex") {
        NSWorkspace.shared.openApplication(
          at: url, configuration: NSWorkspace.OpenConfiguration(), completionHandler: nil)
      }
    case "reload":
      send(["op":"gallery-refresh"])
      if let data = try? Data(contentsOf: s.folder.appendingPathComponent("config.json")),
        let cfg = try? JSONDecoder().decode(Config.self, from: data)
      {
        currentPack = ""
        s.config = cfg
      }
    default: break
    }
  }
  func toggleSleep() {
    endSequence("interrupted")
    pendingNotices.removeAll()
    stopFlight()
    cancel()
    closeCard()
    speech.stopSpeaking(at: .immediate)
    s.config.asleep = !sleeping
    sendConfig()
    if sleeping {
      if let clip = sprite.pickClip(sprite.clipLibrary?.bedtime) {
        _ = sprite.playClip(clip)
      } else {
        sprite.play(.nap)
      }
      bubble?.orderOut(nil)
    } else {
      if let clip = sprite.pickClip(sprite.clipLibrary?.waking) {
        _ = sprite.playClip(clip)
      } else {
        sprite.play(.greet)
      }
      showSpoken("我醒啦。")
    }
  }
  func showTodos() {
    guard !sleeping else { return }
    bubbleTimer?.invalidate()
    send(["op": "todo-list"])
    surface(.todos, focus: true)
  }
  func readAloud(_ text: String) {
    send(["op":"read-aloud","text":text])
  }
  func attachPasteboard(_ pb: NSPasteboard) -> Bool {
    guard !sleeping, s.visionAvailable else { return false }
    if let urls = pb.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true])
      as? [URL], let u = urls.first, ["png", "jpeg", "jpg"].contains(u.pathExtension.lowercased())
    {
      s.attachment = u
      showChat()
      return true
    }
    if let img = NSImage(pasteboard: pb), let data = img.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: data),
      let bytes = bitmap.representation(using: .png, properties: [:]), bytes.count <= 8_388_608
    {
      let u = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString + ".png")
      do {
        try bytes.write(to: u)
        tempImages.insert(u)
        s.attachment = u
        showChat()
        return true
      } catch {}
    }
    return false
  }
  func captureRegion() {
    let u = FileManager.default.temporaryDirectory.appendingPathComponent(
      UUID().uuidString + ".png")
    let job = Process()
    job.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    job.arguments = ["-i", "-x", u.path]
    bubble?.orderOut(nil)
    job.terminationHandler = { [weak self] p in
      DispatchQueue.main.async {
        guard let self = self else { return }
        if p.terminationStatus == 0 && FileManager.default.fileExists(atPath: u.path) {
          self.s.attachment = u
          self.tempImages.insert(u)
        }
        self.showChat()
      }
    }
    do { try job.run() } catch { showChat() }
  }
}

extension Host {
  func installPetInputs() {
    NotificationCenter.default.addObserver(
      forName: NSApplication.didBecomeActiveNotification, object: NSApp, queue: .main
    ) { [weak self] _ in
      guard let self = self, self.card.mode == .compose, self.bubble?.isVisible == true,
        self.settingsWindow?.isKeyWindow != true, self.chatWindow?.isKeyWindow != true
      else { return }
      self.bubble?.makeKey()
      self.refreshHoverKeys()
    }

    outsideClicks = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) {
      [weak self] _ in
      guard let self = self, self.card.mode == .todos || self.card.mode == .compose,
        self.bubble?.isVisible == true
      else { return }
      self.closeCard()
    }
    menuKeys = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
      guard let self = self else { return e }
      if self.card.mode == .compose && self.bubble?.isKeyWindow == true
        && e.modifierFlags.contains([.control, .option]) && e.keyCode == kVK_Space
      {
        if self.card.recording { self.dictation.release() } else { self.dictation.start(self) }
        return nil
      }
      if self.card.mode == .compose && self.bubble?.isKeyWindow == true
        && e.modifierFlags.contains(.command) && e.charactersIgnoringModifiers == "v",
        self.attachPasteboard(.general)
      {
        return nil
      }
      return e
    }
  }
  func idleLife() {
    guard uptime >= nextIdleAction else { return }
    nextIdleAction = uptime + (s.config.roaming == true ? Double.random(in: 14...36) : Double.random(in: 40...76))
    guard s.status == "idle", !leased, !sleeping, !sprite.held, flight == nil, !overPet,
      bubble?.isVisible != true, overlay.isVisible
    else { return }
    if s.config.roaming == true, let screen = overlay.screen {
      let work = travelArea(
        on: screen.visibleFrame, body: overlay.frame,
        displays: NSScreen.screens.map(\.visibleFrame), locked: s.config.lockScreen == true)
      let start = overlay.frame.origin
      let edge = overlay.frame.width * 0.5
      let forward: Double =
        start.x < work.minX + edge
        ? 1 : overlay.frame.maxX > work.maxX - edge ? -1 : Bool.random() ? 1 : -1
      let goal = max(
        work.minX,
        min(work.maxX - overlay.frame.width, start.x + forward * Double.random(in: 70...230)))
      let begin = uptime
      let duration = max(0.4, abs(goal - start.x) / 95)
      sprite.pose(forward > 0 ? "running-right" : "running-left")
      overrideUntil = begin + duration
      flight = Timer.scheduledTimer(withTimeInterval: 1 / 30, repeats: true) { [weak self] _ in
        guard let self = self else { return }
        if self.s.status != "idle" || self.sleeping || self.overPet {
          self.settle()
          return
        }
        let t = min(1, (self.uptime - begin) / duration)
        self.overlay.setFrameOrigin(CGPoint(x: start.x + (goal - start.x) * t, y: start.y))
        self.anchorCard()
        self.sharePose()
        if t >= 1 { self.settle() }
      }
    } else if s.config.randomActions ?? true, let clip = sprite.pickClip(sprite.clipLibrary?.idle) {
      _ = sprite.playClip(clip)
    } else if s.config.randomActions ?? true,
      let trick = PetTrick.allCases.filter({ $0 != .nap }).randomElement()
    {
      if Bool.random(), let scene = PetScene.allCases.filter({ $0.group != "额度" }).randomElement() {
        sprite.playScene(scene)
      } else {
        sprite.play(trick)
      }
    }
  }
}
