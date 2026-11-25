import AppKit

struct PointerTrail {
  private var samples: [(p: CGPoint, t: TimeInterval)] = []
  mutating func reset(_ p: CGPoint, _ t: TimeInterval) { samples = [(p, t)] }
  mutating func append(_ p: CGPoint, _ t: TimeInterval) {
    guard let last = samples.last else {
      reset(p, t)
      return
    }
    if t < last.t {
      reset(p, t)
      return
    }
    guard p != last.p else { return }
    if t - last.t > 0.23 { samples.removeAll() }
    samples.append((p, t))
    samples.removeAll { t - $0.t > 0.75 }
  }

  // Travel along a curved stroke survives even when the mouse ends where it started.
  func launch(at release: CGPoint, time: TimeInterval, force: Double) -> CGVector? {
    guard force.isFinite, force > 0, let last = samples.last, time - last.t < 0.18 else { return nil }
    var points = samples
    if release != last.p { points.append((release, time)) }
    guard let first = points.first, let end = points.last, end.t - first.t >= 0.015 else { return nil }
    let path = zip(points, points.dropFirst()).reduce(0.0) {
      $0 + hypot($1.1.p.x - $1.0.p.x, $1.1.p.y - $1.0.p.y)
    }
    let chord = hypot(end.p.x - first.p.x, end.p.y - first.p.y)
    let span = points.map { hypot($0.p.x - first.p.x, $0.p.y - first.p.y) }.max() ?? 0
    let speed = path / max(0.04, end.t - first.t)
    if points.count >= 4 && span >= 18 && path >= 60 && chord < path * 0.68 && speed >= 180 {
      let direction = Bool.random() ? 1.0 : -1.0
      return CGVector(dx: direction * min(3300, 1650 + speed * 0.8) * force,
                      dy: Double.random(in: 540...940) * force)
    }
    let tail = points.filter { end.t - $0.t <= 0.17 }
    guard let a = tail.first, end.t - a.t >= 0.015 else { return nil }
    let dx = end.p.x - a.p.x, dy = end.p.y - a.p.y
    let distance = hypot(dx, dy)
    let velocity = distance / (end.t - a.t)
    guard distance >= 12, velocity >= 270 else { return nil }
    let gain = min(3500, max(750, velocity * 1.55)) * force / distance
    return CGVector(dx: dx * gain, dy: dy * gain)
  }
}
enum PetTrick: String, CaseIterable {
  case greet = "向你挥手"
  case bow = "骑士礼"
  case dance = "春日小舞"
  case breeze = "唤起微风"
  case stars = "收集星光"
  case read = "翻阅手记"
  case tea = "喝下午茶"
  case cheer = "开心转圈"
  case nap = "打个盹"
  var row: String {
    switch self {
    case .greet, .dance: return "waving"
    case .bow, .read: return "review"
    case .breeze, .tea, .nap: return "waiting"
    case .stars, .cheer: return "jumping"
    }
  }
  var symbol: String? {
    switch self {
    case .breeze: return "wind"
    case .stars: return "sparkles"
    case .read: return "book.fill"
    case .tea: return "cup.and.saucer.fill"
    case .nap: return "moon.zzz.fill"
    default: return nil
    }
  }
}
extension Sprite {
  func look(toward point: CGPoint) {
    guard let host = host, !held, gazeImages.count == 16, row == 0, activeClip == nil,
      !host.sleeping, host.overrideUntil <= host.uptime, host.flight == nil, let f = window?.frame
    else {
      if gaze != nil {
        gaze = nil
        needsDisplay = true
      }
      return
    }
    let dx = point.x - f.midX
    let dy = point.y - f.midY
    let dist = hypot(dx, dy)
    let next: Int? =
      dist > f.width * 0.52 && dist < f.height * 2.6
      ? (Int((atan2(dx, dy) * 8 / Double.pi).rounded()) + 16) % 16 : nil
    if gaze != next {
      gaze = next
      needsDisplay = true
    }
  }
  func renderFrame() {
    guard frames.indices.contains(row) else { return }
    if let clip = activeClip {
      lastPoseRect = bounds
      lastPoseTransform = .identity
      clip.frames[clip.frame].draw(in: bounds)
      return
    }
    var rect = bounds
    let now = ProcessInfo.processInfo.systemUptime
    let t = now - effectStart
    let trick = (host?.sleeping == true) ? PetTrick.nap : (now < effectEnd ? effect : nil)
    let wave = sin(t * 5)
    var angle = gestureLean
    if gestureStretch > 0 {
      rect = rect.insetBy(dx: rect.width * gestureStretch / 2, dy: 0)
      rect.size.height *= 1 + gestureStretch * 0.4
    }
    if let trick = trick {
      switch trick {
      case .bow: angle = -12 * pow(sin(min(t, 2.4) * Double.pi / 2.4), 2)
      case .dance:
        angle = wave * 9
        rect.origin.x = wave * bounds.width * 0.055
      case .cheer:
        rect.origin.y = abs(wave) * bounds.height * 0.07
        angle = wave * 5
      case .nap:
        angle = -8 + sin(t * 1.2)
        rect.size.height *= 0.91
      case .tea, .read: angle = wave * 2
      default: break
      }
    }
    if now < impactEnd {
      let squash = (impactEnd - now) / 0.23 * 0.13
      rect = rect.insetBy(dx: -rect.width * squash / 2, dy: 0)
      rect.size.height *= 1 - squash
    }
    NSGraphicsContext.saveGraphicsState()
    let tr = NSAffineTransform()
    tr.translateX(by: bounds.midX, yBy: bounds.midY)
    tr.rotate(byDegrees: angle)
    tr.translateX(by: -bounds.midX, yBy: -bounds.midY)
    lastPoseRect = rect
    lastPoseTransform = CGAffineTransform(translationX: bounds.midX, y: bounds.midY).rotated(
      by: angle * Double.pi / 180
    ).translatedBy(x: -bounds.midX, y: -bounds.midY)
    tr.concat()
    let image =
      gaze.flatMap { gazeImages.indices.contains($0) ? gazeImages[$0] : nil } ?? frames[row][index]
    image.draw(in: rect)
    NSGraphicsContext.restoreGraphicsState()
    if now < effectEnd { activeScene?.paint(bounds, elapsed: t) }
    if let symbol = trick?.symbol,
      let img = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)?
        .withSymbolConfiguration(.init(paletteColors: [.systemTeal, .systemYellow]))
    {
      let w = bounds.width * 0.22
      img.draw(
        in: NSRect(
          x: bounds.width * 0.65, y: bounds.height * (trick == .nap ? 0.74 : 0.48) + wave * 3,
          width: w, height: w))
    }
  }
  func play(_ trick: PetTrick) {
    activeScene = nil
    effect = trick
    effectStart = ProcessInfo.processInfo.systemUptime
    effectEnd = effectStart + 2.4
    host?.act(trick.row)
    host?.overrideUntil = effectEnd
    needsDisplay = true
  }
  func bump() {
    impactEnd = ProcessInfo.processInfo.systemUptime + 0.23
    needsDisplay = true
  }
}

// Work areas are expressed in global AppKit points, including negative origins.
func travelArea(on current: NSRect, body: NSRect, displays: [NSRect], locked: Bool) -> NSRect {
  guard !locked else { return current }
  var left = current.minX
  var right = current.maxX
  var bottom = current.minY
  var top = current.maxY
  for _ in displays {
    let previous = [left, right, bottom, top]
    for area in displays {
      if body.minY >= area.minY && body.maxY <= area.maxY {
        if abs(right - area.minX) < 1 { right = area.maxX }
        if abs(left - area.maxX) < 1 { left = area.minX }
      }
      if body.minX >= area.minX && body.maxX <= area.maxX {
        if abs(top - area.minY) < 1 { top = area.maxY }
        if abs(bottom - area.maxY) < 1 { bottom = area.minY }
      }
    }
    if previous == [left, right, bottom, top] { break }
  }
  return NSRect(x: left, y: bottom, width: right - left, height: top - bottom)
}
