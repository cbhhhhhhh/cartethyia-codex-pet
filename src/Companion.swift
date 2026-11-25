import AVFoundation
import AppKit
import Carbon
import ImageIO
import SwiftUI
import UserNotifications

let support =
  ProcessInfo.processInfo.environment["PET_PLUS_HOME"].map {
    URL(fileURLWithPath: $0, isDirectory: true)
  }
  ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(
    "Library/Application Support/CodexPetPlus")
let codexDirectory = ProcessInfo.processInfo.environment["CODEX_HOME"].map { URL(fileURLWithPath: $0) }
  ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex")
let packs = codexDirectory.appendingPathComponent("pets")
let shippedPacks = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/pets")

func petDirectory(_ name: String) -> URL {
  let custom = packs.appendingPathComponent(name)
  if FileManager.default.fileExists(atPath: custom.appendingPathComponent("pet.json").path) { return custom }
  return shippedPacks.appendingPathComponent(name)
}
let names = [
  "idle", "running-right", "running-left", "waving", "jumping", "failed", "waiting", "running",
  "review",
]
let counts = [6, 8, 8, 4, 5, 8, 6, 6, 6]
let standardMap = [
  "idle": "idle", "thinking": "review", "working": "running", "waiting-for-approval": "waiting",
  "review": "review", "success": "jumping", "error": "failed",
]
let modelName = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
let titles = [
  "idle": "空闲", "thinking": "思考中", "working": "执行中", "waiting-for-approval": "等待审批",
  "review": "检查结果", "success": "任务完成", "error": "任务失败", "timeout": "已停止接收事件",
]
struct Config: Codable {
  var size = 144.0, x = 80.0, y = 80.0
  var chat = true, whispers = false, notifications = true, sound = false, muted = false,
    focus = false, localTime = false, snap = false
  var voiceWhisper = false, voiceNotice = false, voiceTodo = false, volume = 0.45
  var rounds = 10, minutes = 45, quietStart = 22, quietEnd = 8
  var persona = "你是卡提希娅，一位温柔而坚定的流浪骑士。以第一人称说话，句子简短自然。"
  var model = modelName, pack = "cartethyia", shortcut = "P"
  var weatherCity: String?, weatherEnabled: Bool?, projector: String?
  var roaming: Bool?, randomActions: Bool?, asleep: Bool?, voiceChat: Bool?, voiceName: String?,
    whisperModel: String?
  var gravity: Double?, rebound: Double?, friction: Double?, throwForce: Double?
  var lockScreen: Bool?, replyArt: Bool?, artLimit: Int?, automaticQuota: Bool?, dreams: Bool?
  var mapping = standardMap
}
class CompanionState: ObservableObject {
  @Published var config = Config() { didSet { changed?() } }
  @Published var tasks: [PetTask] = []
  @Published var draft = ""
  @Published var pairs: [ChatPair] = []
  @Published var partial = ""
  @Published var talking = false
  @Published var status = "idle"
  @Published var tool = ""
  @Published var progress = ""
  @Published var thread = ""
  @Published var since = 0.0
  @Published var health = ""
  @Published var quota = ""
  @Published var emotion = ""
  @Published var weather = ""
  var visionAvailable: Bool {
    if !(config.projector ?? "").isEmpty { return true }
    let runtime = support.appendingPathComponent("runtime")
    return ["Qwen3VL-2B-Instruct-Q4_K_M.gguf", "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"].allSatisfy {
      FileManager.default.fileExists(atPath: runtime.appendingPathComponent($0).path)
    }
  }
  @Published var attachment: URL?
  var changed: (() -> Void)?
  var profile = "main"
  var folder: URL { support.appendingPathComponent("profiles/" + profile) }
  var packList: [String] {
    let available = [packs, shippedPacks].flatMap {
      (try? FileManager.default.contentsOfDirectory(atPath: $0.path)) ?? []
    }
    return Set(available).filter {
      FileManager.default.fileExists(atPath: petDirectory($0).appendingPathComponent("pet.json").path)
    }.sorted()
  }
}
class Sprite: NSView {
  weak var host: Host?
  var frames = [[NSImage]](), masks = [[NSBitmapImageRep]]()
  var gazeImages = [NSImage](), gazeMasks = [NSBitmapImageRep](), gaze: Int?
  var gestureLean = 0.0, gestureStretch = 0.0
  var row = 0, index = 0
  var clipRoot: URL?, clipLibrary: ClipLibrary?, clipTimer: Timer?
  var activeClip: ClipPlayer? { didSet { refreshClipTimer() } }
  var lastPoseTransform = CGAffineTransform.identity
  var lastPoseRect: NSRect?
  var activeScene: PetScene?
  var trail = PointerTrail(), sling = false
  var effect: PetTrick?, effectStart = 0.0, effectEnd = 0.0, impactEnd = 0.0
  var start = CGPoint.zero, origin = CGPoint.zero, dragged = false, held = false
  override func isAccessibilityElement() -> Bool { true }
  override func accessibilityRole() -> NSAccessibility.Role? { .button }
  override func accessibilityLabel() -> String? { "卡提希娅，打开聊天" }
  override func accessibilityValue() -> Any? { names[row] }
  override func accessibilityPerformPress() -> Bool {
    host?.tap()
    return true
  }
  override var isFlipped: Bool { false }
  func load(_ pack: String) -> Bool {
    guard !pack.contains("/"), !pack.hasPrefix("."), !pack.isEmpty else { return false }
    let dir = petDirectory(pack)
    guard let d = try? Data(contentsOf: dir.appendingPathComponent("pet.json")),
      let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
      let path = j["spritesheetPath"] as? String
    else { return false }
    let url = dir.appendingPathComponent(path).resolvingSymlinksInPath().standardizedFileURL
    guard url.path.hasPrefix(dir.resolvingSymlinksInPath().path + "/"),
      let source = CGImageSourceCreateWithURL(url as CFURL, nil),
      let atlas = CGImageSourceCreateImageAtIndex(source, 0, nil), atlas.width == 1536,
      [1872, 2288].contains(atlas.height)
    else { return false }
    var all = [[NSImage]]()
    var bitmaps = [[NSBitmapImageRep]]()
    for (r, count) in counts.enumerated() {
      var images = [NSImage]()
      var masks = [NSBitmapImageRep]()
      for c in 0..<count {
        guard let crop = atlas.cropping(to: CGRect(x: c * 192, y: r * 208, width: 192, height: 208))
        else { return false }
        let bitmap = NSBitmapImageRep(cgImage: crop)
        let image = NSImage(size: NSSize(width: 192, height: 208))
        image.addRepresentation(bitmap)
        images.append(image)
        masks.append(bitmap)
      }
      all.append(images)
      bitmaps.append(masks)
    }
    gazeImages = []
    gazeMasks = []
    gaze = nil
    if atlas.height == 2288 {
      for direction in 0..<16 {
        guard
          let c = atlas.cropping(
            to: CGRect(
              x: direction % 8 * 192, y: (9 + direction / 8) * 208, width: 192, height: 208))
        else { continue }
        gazeMasks.append(NSBitmapImageRep(cgImage: c))
        gazeImages.append(NSImage(cgImage: c, size: .zero))
      }
    }
    loadClipLibrary(dir)
    frames = all
    masks = bitmaps
    index = 0
    needsDisplay = true
    return true
  }
  func pose(_ name: String) {
    if name != "idle" { gaze = nil }
    if name.hasPrefix("clip:") {
      let key = String(name.dropFirst(5))
      if activeClip?.key == key || playClip(key, loop: true) { return }
    }
    activeClip = nil
    let next = names.firstIndex(of: name) ?? 0
    if next != row {
      row = next
      index = 0
      needsDisplay = true
    }
  }
  func advance() {
    guard frames.count > row else { return }
    index = (index + 1) % frames[row].count
    needsDisplay = true
  }
  override func draw(_ dirtyRect: NSRect) {
    renderFrame()
  }
  func hit(_ screen: CGPoint) -> Bool {
    guard let w = window, w.frame.contains(screen), masks.count > row else { return false }
    let p = w.convertPoint(fromScreen: screen).applying(lastPoseTransform.inverted())
    let rect = lastPoseRect ?? bounds
    guard rect.contains(p) else { return false }

    let mask =
      activeClip.map { $0.masks[$0.frame] } ?? gaze.flatMap {
        gazeMasks.indices.contains($0) ? gazeMasks[$0] : nil
      } ?? masks[row][index]
    let width = mask.pixelsWide
    let height = mask.pixelsHigh
    let x = min(width - 1, max(0, Int((p.x - rect.minX) / rect.width * Double(width))))
    let y = min(
      height - 1, max(0, height - 1 - Int((p.y - rect.minY) / rect.height * Double(height))))
    return (mask.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.12
  }
  override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
  override func mouseDown(with e: NSEvent) {
    if e.modifierFlags.contains(.control) {
      rightMouseDown(with: e)
      return
    }
    host?.revokeLease()
    host?.stopFlight()
    host?.dismissHover()
    held = true
    dragged = false
    start = window!.convertPoint(toScreen: e.locationInWindow)
    origin = window!.frame.origin
    sling = e.clickCount >= 2
    if sling && host?.card.mode == .compose { host?.closeCard() }
    trail.reset(start, e.timestamp)
  }
  override func mouseDragged(with e: NSEvent) {
    guard let window = window else { return }
    let p = window.convertPoint(toScreen: e.locationInWindow)
    trail.append(p, e.timestamp)
    if hypot(p.x - start.x, p.y - start.y) > 3 { dragged = true }
    if dragged {
      gestureLean = max(-11, min(11, (p.x - start.x) / 12))
      gestureStretch = sling ? min(0.14, hypot(p.x - start.x, p.y - start.y) / 600) : 0
      needsDisplay = true
      host?.place(CGPoint(x: origin.x + p.x - start.x, y: origin.y + p.y - start.y), screenAt: p)
    }
  }
  override func mouseUp(with e: NSEvent) {
    held = false
    gestureLean = 0
    gestureStretch = 0
    needsDisplay = true
    guard let host = host, let window = window else { return }
    let p = window.convertPoint(toScreen: e.locationInWindow)
    let power = host.s.config.throwForce ?? 1
    if dragged {
      if sling && hypot(start.x-p.x, start.y-p.y) > 16 {
        let k = 1200 * power / max(1, bounds.width * 0.6)
        host.fling(CGVector(dx: (start.x - p.x) * k, dy: (start.y - p.y) * k))
      } else if let v = trail.launch(at: p, time: e.timestamp, force: power) {
        host.fling(v)
      } else {
        host.settle()
      }
    } else {
      bump()
      if host.s.config.sound && !host.s.config.muted { NSSound(named: "Tink")?.play() }
      host.tap()
    }
  }
  override func rightMouseDown(with event: NSEvent) {
    guard let host = host else { return }
    host.dismissHover()
    NSMenu.popUpContextMenu(host.petMenu(), with: event, for: self)
  }
  override func menu(for event: NSEvent) -> NSMenu? { host?.petMenu() }
  override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
    host?.s.visionAvailable == true
      && sender.draggingPasteboard.canReadObject(
        forClasses: [NSURL.self, NSImage.self], options: nil)
      ? .copy : []
  }
  override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
    host?.attachPasteboard(sender.draggingPasteboard) ?? false
  }

}
struct Settings: View {
  @ObservedObject var state: CompanionState
  let host: Host
  func option<T>(_ field: WritableKeyPath<Config, T?>, _ value: T) -> Binding<T> {
    Binding(
      get: { state.config[keyPath: field] ?? value }, set: { state.config[keyPath: field] = $0 })
  }
  var body: some View {
    TabView {
      Form {
        Picker("角色", selection: $state.config.pack) {
          ForEach(state.packList, id: \.self) { Text($0).tag($0) }
        }
        Slider(value: $state.config.size, in: 88...288, step: 4) { Text("大小") }
        Button("移到鼠标所在屏幕") { host.resetPosition() }
        Picker("唤醒快捷键 ⌃⌥", selection: $state.config.shortcut) {
          ForEach(["P", "K", "J"], id: \.self) { Text($0).tag($0) }
        }
        Toggle("屏幕边缘吸附", isOn: $state.config.snap)
        Toggle("额度跨档时提示", isOn: option(\.automaticQuota, false))
        Toggle("工作通知", isOn: $state.config.notifications)
        Toggle("提示音", isOn: $state.config.sound)
        Button("启用系统通知") { host.requestNotifications() }
      }.tabItem { Text("桌面") }
      Form {
        Toggle("空闲漫游", isOn: option(\.roaming, false))
        Toggle("随机角色动作", isOn: option(\.randomActions, true))
        Toggle("抛掷和漫游锁定当前屏幕", isOn: option(\.lockScreen, false))
        Slider(value: option(\.gravity, 1400), in: 100...3000, step: 50) { Text("重力") }
        Slider(value: option(\.rebound, 0.78), in: 0.1...0.94, step: 0.02) { Text("弹性") }
        Slider(value: option(\.friction, 2.5), in: 0.5...8, step: 0.25) { Text("地面摩擦") }
        Slider(value: option(\.throwForce, 1), in: 0.25...2, step: 0.05) { Text("甩出力度") }
      }.tabItem { Text("运动") }
      Form {
        Toggle("点击聊天", isOn: $state.config.chat)
        TextField("本地 GGUF 文件名", text: $state.config.model)
        Text("人设")
        TextEditor(text: $state.config.persona).frame(height: 68)
        Stepper(
          "发送给模型最近 " + String(state.config.rounds) + " 轮", value: $state.config.rounds, in: 0...50)
        TextField(
          "可选视觉投影 GGUF",
          text: Binding(get: { state.config.projector ?? "" }, set: { state.config.projector = $0 })
        )
        Toggle("回复附上角色表情", isOn: option(\.replyArt, false))
        Stepper("最多 \(state.config.artLimit ?? 1) 张", value: option(\.artLimit, 1), in: 1...3)
        Toggle("允许使用本地时间", isOn: $state.config.localTime)
      }.tabItem { Text("聊天") }
      Form {
        TextField(
          "城市名称",
          text: Binding(
            get: { state.config.weatherCity ?? "" }, set: { state.config.weatherCity = $0 }))
        Toggle(
          "向 Open-Meteo 查询城市天气",
          isOn: Binding(
            get: { state.config.weatherEnabled ?? false }, set: { state.config.weatherEnabled = $0 }
          ))
        Text("启用后，仅在生成回复时按城市查询，结果缓存一小时。").font(.caption)

      }.tabItem { Text("环境") }
      Form {
        TextField("碎碎念模型（留空跟随聊天）", text: option(\.whisperModel, ""))
        Toggle("允许梦话", isOn: option(\.dreams, false))
        Toggle("空闲时碎碎念", isOn: $state.config.whispers)
        Stepper(
          "间隔 " + String(state.config.minutes) + " 分钟", value: $state.config.minutes, in: 5...240)
        Stepper(
          "安静开始 " + String(state.config.quietStart) + " 时", value: $state.config.quietStart,
          in: 0...23)
        Stepper(
          "安静结束 " + String(state.config.quietEnd) + " 时", value: $state.config.quietEnd, in: 0...23)
        Toggle("专注模式", isOn: $state.config.focus)
        Toggle("静音", isOn: $state.config.muted)
        Toggle("朗读对话与手动碎碎念", isOn: option(\.voiceChat, false))
        Picker("音色", selection: option(\.voiceName, "")) {
          Text("系统中文音色").tag("")
          ForEach(AVSpeechSynthesisVoice.speechVoices(), id: \.identifier) { v in
            Text(v.name + " · " + v.language).tag(v.identifier)
          }
        }
        Toggle("朗读自动碎碎念", isOn: $state.config.voiceWhisper)
        Toggle("朗读通知", isOn: $state.config.voiceNotice)
        Toggle("朗读待办", isOn: $state.config.voiceTodo)
        Slider(value: $state.config.volume, in: 0...1) { Text("音量") }
      }.tabItem { Text("声音与提醒") }
      Form {
        ForEach(standardMap.keys.sorted(), id: \.self) { key in
          Picker(
            titles[key] ?? key,
            selection: Binding(
              get: { state.config.mapping[key] ?? "idle" }, set: { state.config.mapping[key] = $0 })
          ) {
            ForEach(
              names + (host.sprite.clipLibrary?.clips.keys.sorted().map { "clip:" + $0 } ?? []),
              id: \.self
            ) { Text($0).tag($0) }
          }
        }
      }.tabItem { Text("动作") }
    }.padding().frame(width: 475, height: 460)
  }
}
