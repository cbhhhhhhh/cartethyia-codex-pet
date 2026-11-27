import AppKit

extension Host {
  func revokeLease() {
    endSequence("interrupted")
    if leased {
      leased = false
      send(["op": "web-revoke"])
    }
  }
  func external(_ cmd: [String: Any]) {
    guard let op = cmd["op"] as? String else { return }
    let text = String((cmd["text"] as? String ?? "").prefix(2000))
    switch op {
    case "lease":
      leased = cmd["held"] as? Bool == true
      if !leased { endSequence("released") }
      if leased {
        if sleeping { toggleSleep() }
        stopFlight()
        closeCard()
        bubble?.orderOut(nil)
      }
    case "menus": extraMenu = cmd["items"] as? [[String: String]] ?? []
    case "say":
      showSpoken(text)
      if cmd["speak"] as? Bool == true { readAloud(text) }
    case "play":
      if let action = cmd["action"] as? String {
        endSequence("interrupted")
        _ = performNamed(action)
      }
    case "sequence":
      endSequence("interrupted")
      if let id = cmd["id"] as? String, let steps = cmd["steps"] as? [[String: Any]] {
        sequenceID = id
        runSequence(steps, 0)
      }
    case "stop-sequence": endSequence("cancelled")
    case "focus-thread": if let id = cmd["thread"] as? String { openThread(id) }
    case "dismiss": closeCard()
    case "move", "throw":
      if let x = cmd["x"] as? Double, let y = cmd["y"] as? Double {
        if op == "move" {
          stopFlight()
          var point = CGPoint(x: x, y: y)
          if cmd["normalized"] as? Bool == true, let f = overlay.screen?.visibleFrame {
            point = CGPoint(
              x: f.minX + min(1, max(0, x)) * (f.width - overlay.frame.width),
              y: f.minY + min(1, max(0, y)) * (f.height - overlay.frame.height))
          }
          let mode = cmd["mode"] as? String ?? "direct"
          if mode == "spring" || mode == "linear" {
            let start = overlay.frame.origin
            let begin = uptime
            flight = Timer.scheduledTimer(withTimeInterval: 1 / 45, repeats: true) {
              [weak self] _ in
              guard let self = self else { return }
              let t = min(1, (self.uptime - begin) / 0.62)
              let u = mode == "spring" ? min(1, 1 - (1 + 7 * t) * exp(-7 * t)) : t
              self.place(
                t >= 1
                  ? point
                  : CGPoint(
                    x: start.x + (point.x - start.x) * u, y: start.y + (point.y - start.y) * u))
              if t >= 1 { self.settle() }
            }
          } else {
            place(point)
            settle()
          }
        } else {
          fling(CGVector(dx: x, dy: y))
        }
      }
    case "sleep", "wake": if (op == "sleep") != sleeping { toggleSleep() }
    case "chat":
      if !sleeping && !s.talking {
        if let img = cmd["image"] as? String { s.attachment = URL(fileURLWithPath: img) }
        ask(text)
      }
    case "cancel":
      cancel()
      closeCard()
    case "usage", "usage-close", "history-delete", "whisper", "weather", "todo-add", "todo-toggle", "todo-delete":
      send(cmd)
    case "todos": showTodos()
    case "quota":
      let item = NSMenuItem()
      item.representedObject = "quota"
      petCommand(item)
    case "clear": clearChat()
    default: break
    }
  }
}

extension Host {
  func performNamed(_ key: String) -> Bool {
    if let scene = PetScene(rawValue: key) {
      sprite.playScene(scene)
    } else if let trick = PetTrick(rawValue: key) {
      sprite.play(trick)
    } else if names.contains(key) {
      act(key)
    } else {
      let clip = String(key.hasPrefix("clip:") ? key.dropFirst(5) : key[...])
      guard performClip(clip, speak: false) else { return false }
    }
    if stageReady {
      let action = sprite.activeClip.map { "clip:" + $0.key } ?? names[sprite.row]
      send(["op": "display", "action": action])
      if !overlay.isVisible {
        let end = overrideUntil
        DispatchQueue.main.asyncAfter(deadline: .now() + max(0.1, min(30, end - uptime))) {
          [weak self] in
          guard let self = self, !self.overlay.isVisible, self.overrideUntil == end else { return }
          self.send(["op": "display", "action": self.s.config.mapping[self.s.status] ?? "idle"])
        }
      }
    }
    return true
  }
  func endSequence(_ status: String) {
    sequenceTimer?.invalidate()
    sequenceTimer = nil
    guard let id = sequenceID else { return }
    send(["op": "playback", "id": id, "status": status])
    sequenceID = nil
    overrideUntil = 0
  }
  func runSequence(_ steps: [[String: Any]], _ i: Int) {
    guard let id = sequenceID else { return }
    guard i < steps.count else {
      endSequence("completed")
      return
    }
    guard let key = steps[i]["action"] as? String, performNamed(key) else {
      endSequence("unknown-action")
      return
    }
    let duration = max(0.1, min(12, steps[i]["seconds"] as? Double ?? 2.4))
    overrideUntil = uptime + duration
    send(["op": "playback", "id": id, "status": "playing", "index": i])
    sequenceTimer = Timer.scheduledTimer(withTimeInterval: duration, repeats: false) {
      [weak self] _ in self?.runSequence(steps, i + 1)
    }
  }
}
