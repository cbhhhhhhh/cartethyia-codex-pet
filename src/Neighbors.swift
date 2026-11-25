import AppKit

extension Host {
  func sharePose() {
    guard peersPresent, uptime >= nextPose else { return }
    nextPose = uptime + (flight != nil || sprite.held ? 0.08 : 1.2)
    let f = overlay.frame
    send([
      "op": "peer", "kind": "pose", "x": f.minX, "y": f.minY, "w": f.width, "h": f.height,
      "visible": overlay.isVisible,
    ])
  }
  func peerEvent(_ m: [String: Any]) {
    guard let from = m["from"] as? String, from != s.profile else { return }
    if m["kind"] as? String == "impulse", m["target"] as? String == s.profile, !sprite.held,
      !sleeping, overlay.isVisible,
      let x = m["vx"] as? Double, let y = m["vy"] as? Double
    {
      lastCollision[from] = uptime
      sprite.bump()
      fling(CGVector(dx: x, dy: y))
    } else if let x = m["x"] as? Double, let y = m["y"] as? Double, let w = m["w"] as? Double,
      let h = m["h"] as? Double
    {
      if m["visible"] as? Bool == false {
        peers[from] = nil
      } else {
        peers[from] = (NSRect(x: x, y: y, width: w, height: h), uptime)
      }
    }
  }
  func collide(_ at: CGPoint, _ v: inout CGVector) {
    guard peersPresent else { return }
    let moving = NSRect(origin: at, size: overlay.frame.size)
    for (profile, (other, t)) in peers
    where uptime - t < 3 && uptime - (lastCollision[profile] ?? -10) > 0.45 {
      let dx = other.midX - moving.midX
      let dy = other.midY - moving.midY
      let radius = (min(other.width, other.height) + min(moving.width, moving.height)) * 0.30
      let length = hypot(dx, dy)
      guard length > 0.1, length < radius else { continue }
      let nx = dx / length
      let ny = dy / length
      let speed = v.dx * nx + v.dy * ny
      guard speed > 28 else { continue }
      let impulse = speed * 0.88
      v.dx -= impulse * nx
      v.dy -= impulse * ny
      send([
        "op": "peer", "kind": "impulse", "target": profile, "vx": impulse * nx, "vy": impulse * ny,
      ])
      sprite.bump()
      lastCollision[profile] = uptime
    }
  }
}
