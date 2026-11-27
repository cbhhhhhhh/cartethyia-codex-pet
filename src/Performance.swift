import AppKit

extension Host {
  @discardableResult func performClip(_ name: String, speak: Bool) -> Bool {
    guard let spec = sprite.clipLibrary?.clips[name], sprite.playClip(name) else { return false }
    send(["op": "performed", "clip": name])
    if let travel = spec.travel, overlay.isVisible, !sprite.held, s.status == "idle" {
      startClipTravel(travel, name: name, duration: Double(spec.frames) / max(1, spec.fps ?? 10))
    }
    if speak && uptime - lastCue >= 6 {
      let start = sprite.activeClip?.start
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.66) { [weak self] in
        guard let self = self, self.sprite.activeClip?.start == start, !self.sleeping,
          !self.s.talking, !self.s.config.muted, self.s.status == "idle",
          self.bubble?.isVisible != true || self.card.mode == .speech else { return }
        self.send(["op":"action-line", "clip":name])
      }
    }
    return true
  }

  private func startClipTravel(_ motion: String, name: String, duration: Double) {
    guard let screen = overlay.screen else { return }
    stopFlight()
    let start = overlay.frame.origin, size = overlay.frame.size
    let region = travelArea(on: screen.visibleFrame, body: overlay.frame,
                            displays: NSScreen.screens.map(\.visibleFrame), locked: s.config.lockScreen == true)
    let right = region.maxX - size.width - start.x, left = start.x - region.minX
    let direction: CGFloat = right < 70 ? -1 : left < 70 ? 1 : Bool.random() ? 1 : -1
    let distance = min(motion == "float" ? 70.0 : 126.0, max(0, direction > 0 ? right : left))
    let rise = min(44.0, max(0, region.maxY - size.height - start.y))
    let begin = uptime
    flight = Timer.scheduledTimer(withTimeInterval: 1 / 30, repeats: true) { [weak self] _ in
      guard let self = self else { return }
      let t = min(1, (self.uptime - begin) / duration)
      guard self.sprite.activeClip?.key == name, !self.sprite.held, !self.sleeping,
        self.overlay.isVisible, self.s.status == "idle" else { self.settle(); return }
      let offset = motion == "return" ? sin(.pi * t) : t*t*(3-2*t)
      self.place(CGPoint(x:start.x + direction*distance*offset,
                         y:start.y + (motion == "float" ? rise * sin(.pi*t) : 0)))
      self.sharePose()
      if t >= 1 { self.settle() }
    }
  }
}
