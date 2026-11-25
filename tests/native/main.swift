import AppKit
import Foundation
import ImageIO
import UniformTypeIdentifiers

// The harness runs our production NSPanel, sprite atlas, broker and mouse handlers.
// Its support directory, rollouts, socket, preferences and notification switches are isolated.
let app = NSApplication.shared
let host = Host()
let env = ProcessInfo.processInfo.environment
let root = URL(fileURLWithPath: env["PET_PLUS_HOME"]!)
var report = [String: Any]()
func check(_ ok: Bool, _ evidence: String) {
  if !ok {
    FileHandle.standardError.write(Data(("FAILED " + evidence + "\n").utf8))
    exit(1)
  }
  report[evidence] = true
}
func spin(_ seconds: Double) {
  let until = Date().addingTimeInterval(seconds)
  while Date() < until {
    while let event = app.nextEvent(
      matching: .any, until: .distantPast, inMode: .default, dequeue: true)
    { app.sendEvent(event) }
    RunLoop.main.run(until: min(until, Date().addingTimeInterval(0.005)))
  }
}
func wait(_ condition: () -> Bool) -> Double {
  let a = ProcessInfo.processInfo.systemUptime
  while !condition() && ProcessInfo.processInfo.systemUptime - a < 2.5 { spin(0.003) }
  return (ProcessInfo.processInfo.systemUptime - a) * 1000
}
func snapshot(_ label: String) {
  guard let panel = host.bubble, panel.isVisible, let view = panel.contentView else { return }
  view.layoutSubtreeIfNeeded()
  host.sprite.displayIfNeeded()
  let area = host.overlay.frame.union(panel.frame).insetBy(dx: -8, dy: -8)
  let image = NSImage(size: area.size)
  image.lockFocus()
  NSColor(calibratedRed: 0.93, green: 0.94, blue: 0.89, alpha: 1).setFill()
  NSRect(origin: .zero, size: area.size).fill()
  for (v, f) in [(host.sprite as NSView, host.overlay.frame), (view, panel.frame)] {
    guard let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { continue }
    v.cacheDisplay(in: v.bounds, to: rep)
    let rendered = NSImage(size: v.bounds.size)
    rendered.addRepresentation(rep)
    rendered.draw(
      in: f.offsetBy(dx: -area.minX, dy: -area.minY), from: .zero, operation: .sourceOver,
      fraction: 1)
  }
  image.unlockFocus()
  if let t = image.tiffRepresentation,
    let png = NSBitmapImageRep(data: t)?.representation(using: .png, properties: [:])
  {
    try? png.write(
      to: URL(fileURLWithPath: env["PET_PLUS_PREVIEW"]!).deletingLastPathComponent()
        .appendingPathComponent("v21-" + label + ".png"))
  }
}
let thread = UUID().uuidString.lowercased()
var turn = UUID().uuidString.lowercased()
func hook(_ kind: String) {
  let p = Process()
  let input = Pipe()
  p.executableURL = Bundle.main.executableURL!.deletingLastPathComponent().appendingPathComponent(
    "pet-hook")
  p.standardOutput = FileHandle.nullDevice
  p.standardInput = input
  try! p.run()
  var j = [
    "hook_event_name": kind, "session_id": thread, "turn_id": turn, "tool_use_id": "qa-call",
    "tool_name": "demo",
  ]
  if kind == "PermissionRequest" { j.removeValue(forKey: "tool_use_id") }
  try! input.fileHandleForWriting.write(contentsOf: JSONSerialization.data(withJSONObject: j))
  try! input.fileHandleForWriting.close()
}
func transition(_ name: String, _ state: String, _ pose: String) {
  let start = ProcessInfo.processInfo.systemUptime
  hook(name)
  _ = wait { host.s.status == state && names[host.sprite.row] == pose }
  host.sprite.displayIfNeeded()
  let latency = (ProcessInfo.processInfo.systemUptime - start) * 1000
  if latency >= 1000 {
    FileHandle.standardError.write(
      Data(
        ("expected " + state + ", observed " + host.s.status + ", broker "
          + ((try? String(
            contentsOf: root.appendingPathComponent("profiles/main/status.json"), encoding: .utf8))
            ?? "offline") + "\n").utf8))
  }
  check(
    latency < 1000 && host.s.status == state && names[host.sprite.row] == pose, name + "-" + state)
  report[name + "_ms"] = Int(latency.rounded())
}
func mouse(_ kind: NSEvent.EventType, _ screen: CGPoint, _ clicks: Int = 1) -> NSEvent {
  NSEvent.mouseEvent(
    with: kind, location: host.overlay.convertPoint(fromScreen: screen), modifierFlags: [],
    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: host.overlay.windowNumber,
    context: nil, eventNumber: 0, clickCount: clicks, pressure: 1)!
}
let locked =
  (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool
  ?? false
let phase = CommandLine.arguments.last ?? ""
app.setActivationPolicy(.accessory)
app.delegate = host
_ = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: false) { _ in
  if phase == "actions" {
    host.s.config.notifications = false
    host.s.config.randomActions = false
    host.s.config.roaming = false
    let actions = [
      ("骑士礼", "trick:"), ("春日小舞", "trick:"), ("祈愿水环", "scene:"), ("初雪", "scene:"),
      ("打个盹", "trick:"),
    ]
    let frames = 14
    let path = URL(fileURLWithPath: env["PET_PLUS_PREVIEW"]!).deletingLastPathComponent()
      .appendingPathComponent("v2-actions.gif")
    guard
      let gif = CGImageDestinationCreateWithURL(
        path as CFURL, UTType.gif.identifier as CFString, frames * actions.count, nil)
    else {
      check(false, "gif_destination")
      return
    }
    CGImageDestinationSetProperties(
      gif, [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]] as CFDictionary)
    for (label, prefix) in actions {
      let item = NSMenuItem()
      item.representedObject = prefix + label
      host.petCommand(item)
      for _ in 0..<frames {
        spin(0.15)
        host.sprite.displayIfNeeded()
        let snap = host.sprite.bitmapImageRepForCachingDisplay(in: host.sprite.bounds)!
        host.sprite.cacheDisplay(in: host.sprite.bounds, to: snap)
        let img = NSImage(size: NSSize(width: 200, height: 205))
        img.lockFocus()
        NSColor(calibratedRed: 0.96, green: 0.95, blue: 0.91, alpha: 1).setFill()
        NSRect(x: 0, y: 0, width: 200, height: 205).fill()
        let body = NSImage(size: host.sprite.bounds.size)
        body.addRepresentation(snap)
        body.draw(
          in: NSRect(x: 24, y: 30, width: 152, height: 164), from: .zero, operation: .sourceOver,
          fraction: 1)
        let attrs: [NSAttributedString.Key: Any] = [
          .font: NSFont.systemFont(ofSize: 13, weight: .medium),
          .foregroundColor: NSColor(calibratedRed: 0.2, green: 0.32, blue: 0.27, alpha: 1),
        ]
        let title = NSAttributedString(string: label, attributes: attrs)
        title.draw(at: NSPoint(x: (200 - title.size().width) / 2, y: 9))
        img.unlockFocus()
        var r = NSRect(origin: .zero, size: img.size)
        let frame = img.cgImage(forProposedRect: &r, context: nil, hints: nil)!
        CGImageDestinationAddImage(
          gif, frame,
          [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFDelayTime: 0.15]] as CFDictionary)
      }
    }
    check(CGImageDestinationFinalize(gif), "five_choreographies_rendered")
  } else if phase == "recovery" {
    host.s.config.notifications = false
    transition("PreToolUse", "working", "running")
    let old = host.process!.processIdentifier
    kill(old, SIGKILL)
    _ = wait { host.s.status == "idle" }
    check(host.s.status == "idle" && host.sprite.row == 0, "broker_death_resets_sprite")
    _ = wait { host.process?.processIdentifier != old && host.process?.isRunning == true }
    spin(0.35)
    transition("UserPromptSubmit", "thinking", "review")
    check(host.process?.processIdentifier != old, "broker_restarted")
  } else if phase == "real-cli" {
    host.s.config.notifications = false
    let job = Process()
    job.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    job.arguments = ["-B", env["PET_PLUS_CLI_TEST"]!]
    try! job.run()
    var times = [String: Double]()
    let deadline = Date().addingTimeInterval(20)
    while Date() < deadline {
      spin(0.005)
      let state = host.s.status
      if times[state] == nil && (state != "idle" || times["success"] != nil) {
        host.sprite.displayIfNeeded()
        times[state] = Date().timeIntervalSince1970
      }
      if times["idle"] != nil && !job.isRunning { break }
    }
    let store = URL(fileURLWithPath: env["CODEX_HOME"]!).appendingPathComponent("sessions")
    let logs =
      (FileManager.default.enumerator(at: store, includingPropertiesForKeys: nil)?.allObjects
        as? [URL]) ?? []
    var stamps = [String: Double]()
    let dates = ISO8601DateFormatter()
    dates.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    for path in logs where path.pathExtension == "jsonl" {
      for line in ((try? String(contentsOf: path, encoding: .utf8)) ?? "").split(separator: "\n") {
        guard let obj = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
          obj["type"] as? String == "event_msg",
          let body = obj["payload"] as? [String: Any], let kind = body["type"] as? String,
          let str = obj["timestamp"] as? String, let date = dates.date(from: str)
        else { continue }
        stamps[kind] = date.timeIntervalSince1970
      }
    }
    check(
      FileManager.default.fileExists(atPath: root.appendingPathComponent("real-cli-ok").path),
      "real_cli_completed_locally")
    guard let start = stamps["task_started"], let end = stamps["task_complete"],
      let seen = times["thinking"], let idle = times["idle"]
    else {
      FileHandle.standardError.write(
        Data(
          ("Observed states " + times.keys.sorted().joined(separator: ",") + "; records "
            + stamps.keys.sorted().joined(separator: ",") + "\n").utf8))
      exit(1)
    }
    let startMs = Int((seen - start) * 1000)
    let endMs = Int((idle - end) * 1000)
    report["real_start_to_sprite_ms"] = startMs
    report["real_end_to_idle_sprite_ms"] = endMs
    check((0..<1000).contains(startMs) && (0..<1000).contains(endMs), "real_cli_under_1s")
  } else if phase == "restore" {
    check(
      host.s.config.size == 168 && host.s.config.persona == "本机测试卡提"
        && host.overlay.frame.height == 168, "restart_restores_settings")
  } else {
    check(
      FileManager.default.fileExists(atPath: root.appendingPathComponent("events.sock").path),
      "isolated_broker_ready")
    host.s.config.notifications = false
    host.s.config.whispers = false
    check(
      host.overlay.isVisible && !host.overlay.isOpaque && host.overlay.level == .floating
        && host.overlay.styleMask.contains(.borderless), "visible_transparent_floating_window")
    transition("UserPromptSubmit", "thinking", "review")
    transition("PreToolUse", "working", "running")
    transition("PermissionRequest", "waiting-for-approval", "waiting")
    transition("PostToolUse", "thinking", "review")
    let end = ProcessInfo.processInfo.systemUptime
    transition("Stop", "review", "review")
    _ = wait { host.s.status == "idle" && host.sprite.row == 0 }
    host.sprite.displayIfNeeded()
    let latency = (ProcessInfo.processInfo.systemUptime - end) * 1000
    check(latency < 1000 && host.s.status == "idle", "end_to_idle")
    report["unconfirmed_stop_to_idle_ms"] = Int(latency.rounded())
    turn = UUID().uuidString.lowercased()
    transition("UserPromptSubmit", "thinking", "review")
    transition("Interrupt", "idle", "idle")
    let date = DateFormatter()
    date.dateFormat = "yyyy/MM/dd"
    let dir = URL(fileURLWithPath: env["CODEX_HOME"]!).appendingPathComponent(
      "sessions/" + date.string(from: Date()))
    try! FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let f = dir.appendingPathComponent("rollout-" + thread + ".jsonl")
    let stamp = ISO8601DateFormatter()
    stamp.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let errorRecord: [String: Any] = [
      "timestamp": stamp.string(from: Date()), "type": "event_msg",
      "payload": ["type": "error", "turn_id": UUID().uuidString.lowercased()],
    ]
    try! (JSONSerialization.data(withJSONObject: errorRecord) + Data([10])).write(to: f)
    let errTime = wait { host.s.status == "error" && names[host.sprite.row] == "failed" }
    check(errTime < 1000 && host.s.status == "error", "jsonl_error_to_failed")
    report["jsonl_error_ms"] = Int(errTime.rounded())
    spin(0.9)
    check(host.s.status == "idle", "error_expires")
    let mid = CGPoint(x: host.overlay.frame.midX, y: host.overlay.frame.midY)
    let transparent = CGPoint(x: host.overlay.frame.minX + 1, y: host.overlay.frame.maxY - 1)
    check(host.sprite.hit(mid) && !host.sprite.hit(transparent), "alpha_hit_test")
    host.updateHit(transparent)
    check(host.overlay.ignoresMouseEvents, "window_passes_transparent_pixel")
    host.updateHit(mid)
    check(!host.overlay.ignoresMouseEvents, "window_accepts_character_pixel")
    report["physical_displays"] = NSScreen.screens.count
    let screen = host.overlay.screen!.visibleFrame
    let size = host.overlay.frame.size
    let oldPointer = NSEvent.mouseLocation
    func movePointer(_ pt: CGPoint) {
      CGWarpMouseCursorPosition(CGPoint(x: pt.x, y: NSScreen.screens[0].frame.maxY - pt.y))
    }
    func dispatch(_ kind: NSEvent.EventType, _ pt: CGPoint, _ clicks: Int = 1) {
      movePointer(pt)
      app.sendEvent(mouse(kind, pt, clicks))
    }
    func center() -> CGPoint { CGPoint(x: host.overlay.frame.midX, y: host.overlay.frame.midY) }
    movePointer(mid)
    _ = wait { host.bubble?.isVisible == true && host.card.mode == .hover }
    check(
      host.bubble?.parent === host.overlay && host.card.mode == .hover,
      "pointer_opens_anchored_detail_panel")
    turn = UUID().uuidString.lowercased()
    hook("UserPromptSubmit")
    _ = wait { host.s.status == "thinking" }
    let context: [String: Any] = [
      "timestamp": stamp.string(from: Date()), "type": "turn_context", "payload": ["turn_id": turn],
    ]
    let arguments =
      #"{"plan":[{"step":"勘察","status":"completed"},{"step":"验证","status":"in_progress"}]}"#
    let planned: [String: Any] = [
      "timestamp": stamp.string(from: Date()), "type": "response_item",
      "payload": [
        "type": "function_call", "name": "update_plan", "call_id": "qa-plan",
        "arguments": arguments,
      ],
    ]
    let fp = try! FileHandle(forWritingTo: f)
    fp.seekToEndOfFile()
    for record in [context, planned] {
      try! fp.write(contentsOf: JSONSerialization.data(withJSONObject: record) + Data([10]))
    }
    try! fp.close()
    _ = wait { host.s.progress.contains("1/2") }
    hook("PreToolUse")
    _ = wait { host.s.tool == "demo" }
    check(
      host.card.mode == .hover && host.s.since > 0 && host.s.tool == "demo"
        && host.s.progress.contains("1/2"), "hover_live_tool_elapsed_and_plan")
    spin(0.12)
    snapshot("hover")
    hook("Interrupt")
    _ = wait { host.s.status == "idle" }
    let reference = CGPoint(x: screen.midX - 140, y: screen.midY)
    dispatch(.leftMouseDown, mid)
    dispatch(.leftMouseDragged, reference)
    spin(0.21)
    dispatch(.leftMouseUp, reference)
    spin(0.35)
    check(
      host.flight == nil && hypot(center().x - reference.x, center().y - reference.y) < 2,
      "drag_pause_places_in_midair_via_window_events")
    let circleStart = center()
    dispatch(.leftMouseDown, circleStart)
    for i in 1...20 {
      let theta = 2 * Double.pi * Double(i) / 20
      spin(0.014)
      dispatch(.leftMouseDragged, CGPoint(x: circleStart.x + 32*(cos(theta)-1),
                                         y: circleStart.y + 32*sin(theta)))
    }
    dispatch(.leftMouseUp, circleStart)
    check(host.flight != nil, "closed_circle_release_starts_flight")
    var prev = center().x
    var firstSign = 0.0
    var touchedWall = false
    var bounced = false
    let deadline = host.uptime + 2.5
    while host.uptime < deadline && !bounced {
      spin(0.017)
      let frame = host.overlay.frame
      let delta = frame.midX-prev
      if firstSign == 0 && abs(delta)>3 { firstSign = delta > 0 ? 1 : -1 }
      if min(frame.minX-screen.minX, screen.maxX-frame.maxX) < 75 { touchedWall = true }
      if touchedWall && firstSign*delta < -2 { bounced = true }
      prev = frame.midX
    }
    check(bounced, "closed_circle_hits_side_wall_and_rebounds")
    host.stopFlight()
    host.place(CGPoint(x: reference.x-size.width/2,y: reference.y-size.height/2))
    var shake = PointerTrail()
    shake.reset(.zero, 10)
    for (i,x) in [25.0, -10, 22, -6, 0].enumerated() {
      shake.append(CGPoint(x: x,y: 0),10+Double(i+1)*0.033)
    }
    let impulse = shake.launch(at: .zero,time:10.17,force:1)
    check(abs(impulse?.dx ?? 0)>1000, "back_and_forth_shake_launches")
    check(shake.launch(at:.zero,time:10.42,force:1)==nil, "pause_after_fast_gesture_still_parks")
    var menuShown = false
    let monitor = NotificationCenter.default.addObserver(
      forName: NSMenu.didBeginTrackingNotification, object: nil, queue: nil
    ) { n in
      if let menu = n.object as? NSMenu, menu.items.contains(where: { $0.title.contains("待办事项") }) {
        menuShown = true
        DispatchQueue.main.async { menu.cancelTracking() }
      }
    }
    dispatch(.rightMouseDown, center())
    NotificationCenter.default.removeObserver(monitor)
    check(menuShown, "real_context_menu_began_tracking")
    func menuAction(_ command: String) {
      guard
        let item = host.petMenu().items.first(where: { $0.representedObject as? String == command })
      else {
        check(false, "missing-menu-" + command)
        return
      }
      _ = app.sendAction(item.action!, to: item.target, from: item)
    }
    menuAction("todos")
    spin(0.08)
    check(
      host.card.mode == .todos && host.bubble?.parent === host.overlay,
      "context_menu_opens_todo_card")
    host.closeCard()
    menuAction("sleep")
    check(host.sleeping && host.bubble?.isVisible != true, "sleep_from_context_menu")
    dispatch(.leftMouseDown, center())
    dispatch(.leftMouseUp, center())
    check(!host.sleeping, "click_wakes_sleeping_pet")
    host.closeCard()
    let scene = NSMenuItem()
    scene.representedObject = "scene:祈愿水环"
    host.petCommand(scene)
    check(
      host.sprite.activeScene == .ward && names[host.sprite.row] == "jumping",
      "cartethyia_tide_scene")
    let f0 = NSRect(x: 0, y: 0, width: 1000, height: 800)
    let f1 = NSRect(x: 1000, y: 200, width: 900, height: 550)
    let f2 = NSRect(x: -1000, y: 0, width: 850, height: 800)
    let body = NSRect(x: 880, y: 350, width: 100, height: 144)
    check(
      travelArea(on: f0, body: body, displays: [f0, f1, f2], locked: false).maxX == 1900
        && travelArea(on: f0, body: body, displays: [f0, f1, f2], locked: false).minX == 0,
      "connected_display_seam_and_gap_geometry")
    check(
      travelArea(on: f0, body: body, displays: [f0, f1], locked: true) == f0,
      "lock_to_display_geometry")
    let slingStart = center()
    dispatch(.leftMouseDown, slingStart, 2)
    let pull = CGPoint(x: slingStart.x + 65, y: slingStart.y)
    dispatch(.leftMouseDragged, pull, 2)
    dispatch(.leftMouseUp, pull, 2)
    spin(0.08)
    check(host.flight != nil && center().x < pull.x - 5, "double_drag_launches_opposite")
    host.stopFlight()
    let left = CGPoint(x: screen.maxX - size.width / 2 - 115, y: screen.minY + size.height / 2 + 45)
    host.place(CGPoint(x: left.x - size.width / 2, y: left.y - size.height / 2))
    dispatch(.leftMouseDown, center())
    for i in 1...5 {
      spin(0.015)
      dispatch(.leftMouseDragged, CGPoint(x: left.x + CGFloat(i * 18), y: left.y - CGFloat(i * 4)))
    }
    dispatch(.leftMouseUp, CGPoint(x: left.x + 90, y: left.y - 20))
    check(host.flight != nil, "horizontal_swipe_starts_flight_via_window_events")
    movePointer(oldPointer)
    var rebounded = false
    var wallRebounded = false
    var floorRebounded = false
    var contained = true
    var last = host.overlay.frame.origin
    let start = ProcessInfo.processInfo.systemUptime
    while ProcessInfo.processInfo.systemUptime - start < 8 && host.flight != nil {
      spin(0.02)
      let f = host.overlay.frame
      contained = contained && screen.insetBy(dx: -0.1, dy: -0.1).contains(f)
      if f.minY > last.y + 1 { floorRebounded = true }
      if f.minX < last.x - 1 { wallRebounded = true }
      rebounded = wallRebounded && floorRebounded
      last = f.origin
    }
    check(contained && rebounded, "edge_and_floor_rebound")
    check(
      host.flight == nil && abs(host.overlay.frame.minY - screen.minY) < 1, "floor_friction_settles"
    )
    host.s.config.size = 168
    host.s.config.persona = "本机测试卡提"
    check(host.overlay.frame.height == 168, "settings_apply_immediately")
    host.toggle()
    check(
      !host.overlay.isVisible && host.anim?.isValid == false && host.hitTimer?.isValid != true
        && host.globalMouse == nil,
      "hidden_timers_stopped")
    host.toggle()
    let point = CGPoint(x: host.overlay.frame.midX, y: host.overlay.frame.midY)
    movePointer(point)
    spin(0.35)
    dispatch(.leftMouseDown, point)
    dispatch(.leftMouseUp, point)
    spin(0.2)
    FileHandle.standardError.write(
      Data(
        "card=\(host.card.mode), visible=\(host.bubble?.isVisible==true), key=\(host.bubble?.isKeyWindow==true), app=\(app.isActive), parent=\(host.bubble?.parent===host.overlay), hit=\(host.sprite.hit(point))\n"
          .utf8))
    check(
      host.chatWindow == nil && host.card.mode == .compose && host.bubble?.parent === host.overlay
        && host.bubble?.isVisible == true, "click_opens_attached_composer")
    snapshot("input")
    host.s.draft = "你好，请用一句话打招呼。"
    let originalPairCount = host.s.pairs.count
    let inputKey = NSEvent.keyEvent(
      with: .keyDown, location: .zero, modifierFlags: [], timestamp: host.uptime,
      windowNumber: host.bubble!.windowNumber, context: nil, characters: "\r",
      charactersIgnoringModifiers: "\r", isARepeat: false, keyCode: 36)!
    spin(0.22)
    report["screen_locked_during_test"] = locked
    report["composer_has_system_key_focus"] = host.bubble?.isKeyWindow == true
    if locked {
      func field(_ v: NSView) -> NSTextField? {
        if let f = v as? PetInput.Field { return f }
        for child in v.subviews { if let f = field(child) { return f } }
        return nil
      }
      guard let f = field(host.bubble!.contentView!) else {
        check(false, "composer_text_field_present")
        return
      }
      host.bubble!.makeFirstResponder(f)
      if let editor = f.currentEditor() {
        editor.insertNewline(nil)
      } else {
        f.performClick(nil)
        host.bubble!.sendEvent(inputKey)
      }
    } else {
      check(host.bubble?.isKeyWindow == true, "unlocked_composer_receives_keys")
      app.sendEvent(inputKey)
    }
    let until = Date().addingTimeInterval(90)
    var partialSeen = false
    while Date() < until && !(host.s.pairs.count > originalPairCount && !host.s.talking) {
      spin(0.02)
      if host.card.speaker == "本地对话"
        || (host.s.pairs.count == originalPairCount && !host.s.talking && host.card.mode == .speech)
      {
        break
      }
      if host.card.mode == .speech && host.s.talking && host.card.message.count > 1 {
        partialSeen = true
      }
    }
    if host.s.pairs.count == originalPairCount {
      FileHandle.standardError.write(
        Data(
          "reply missing: \(host.card.mode), \(host.card.speaker), \(host.card.message), \(host.s.health),talking=\(host.s.talking), lines=\(host.s.pairs.count)\n"
            .utf8))
    }
    check(
      host.s.pairs.count > originalPairCount && host.card.mode == .speech && host.chatWindow == nil
        && host.card.message == host.s.pairs.last?.assistant && !host.card.message.isEmpty,
      "return_key_produces_actual_model_response_over_pet")
    check(host.card.mood == CardMood(emotion: host.s.emotion) && !host.lastChatGesture.isEmpty,
          "local_reply_selects_emotional_portrait_and_character_gesture")
    let previous = host.lastChatGesture
    host.handle(["type":"reply","text":host.card.message,"emotion":host.s.emotion,"action":"idle"])
    check(!host.lastChatGesture.isEmpty && host.lastChatGesture != previous, "consecutive_chat_gestures_vary")
    report["intermediate_text_observed"] = partialSeen
    snapshot("reply")
    movePointer(oldPointer)
    if let library = host.sprite.clipLibrary, library.clips["牵着线放风筝"] != nil {
      check(
        library.clips.count == 109 && host.sprite.playClip("牵着线放风筝")
          && host.sprite.activeClip?.frames.count == 16, "full_109_action_library_plays_native_clip"
      )
      check(host.sprite.clipTimer?.isValid == true, "custom_clip_uses_its_frame_rate")
    }
    host.stopFlight()
    host.s.status = "idle"
    host.overrideUntil = 0
    host.sprite.pose("idle")
    host.sprite.look(
      toward: CGPoint(
        x: host.overlay.frame.midX + host.overlay.frame.width * 1.1, y: host.overlay.frame.midY))
    check(
      host.sprite.gazeImages.count == 16 && host.sprite.gaze == 4,
      "v2_character_tracks_pointer_to_right")
    host.sprite.look(toward: center())
    host.settings()
    check(host.settingsWindow?.isVisible == true, "settings_window_opens")
    let image = host.sprite.bitmapImageRepForCachingDisplay(in: host.sprite.bounds)!
    host.sprite.cacheDisplay(in: host.sprite.bounds, to: image)
    try! image.representation(using: .png, properties: [:])!.write(
      to: URL(fileURLWithPath: env["PET_PLUS_PREVIEW"]!))
  }
  let bytes = try! JSONSerialization.data(
    withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
  FileHandle.standardOutput.write(bytes)
  app.terminate(nil)
}
app.run()
