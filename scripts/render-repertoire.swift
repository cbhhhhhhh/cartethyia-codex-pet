import AppKit
import Foundation
import ImageIO
import UniformTypeIdentifiers

struct Score: Decodable {
  let id: String, group: String, title: String, pose: String, motion: String, prop: String,
    path: String
}
let width = 192
let height = 208
let frameCount = 16
let names = [
  "idle", "running-right", "running-left", "waving", "jumping", "failed", "waiting", "running",
  "review",
]
let counts = [6, 8, 8, 4, 5, 8, 6, 6, 6]
let pi = Double.pi
let ink = NSColor(calibratedRed: 0.28, green: 0.48, blue: 0.46, alpha: 0.8)
let light = NSColor(calibratedRed: 0.91, green: 0.78, blue: 0.43, alpha: 0.9)
func stroke(_ from: CGPoint, _ to: CGPoint, _ color: NSColor, _ weight: Double = 1.4) {
  let p = NSBezierPath()
  p.move(to: from)
  p.line(to: to)
  p.lineWidth = weight
  p.lineCapStyle = .round
  color.setStroke()
  p.stroke()
}
func glyph(
  _ value: String, _ x: Double, _ y: Double, _ size: Double, _ angle: Double = 0,
  _ alpha: Double = 1
) {
  guard size > 1, alpha > 0 else { return }
  NSGraphicsContext.saveGraphicsState()
  defer { NSGraphicsContext.restoreGraphicsState() }
  let tr = NSAffineTransform()
  tr.translateX(by: x, yBy: y)
  tr.rotate(byDegrees: angle)
  tr.concat()
  NSGraphicsContext.current?.cgContext.setAlpha(alpha)
  let label = NSAttributedString(
    string: value, attributes: [.font: NSFont.systemFont(ofSize: size), .foregroundColor: ink])
  let bounds = label.size()
  label.draw(at: CGPoint(x: -bounds.width / 2, y: -bounds.height / 2))
}
func paintProp(_ cue: Score, _ t: Double) {
  let s = sin(2 * pi * t)
  let c = cos(2 * pi * t)
  let rise = sin(pi * t)
  let phase = 2 * pi * t
  let x = 122.0
  let y = 96.0
  func mark(_ x: Double, _ y: Double, _ size: Double = 24, _ a: Double = 0, _ opacity: Double = 1) {
    glyph(cue.prop, x, y, size, a, opacity)
  }
  func glint(_ x: Double, _ y: Double, _ radius: Double) {
    stroke(.init(x: x - radius, y: y), .init(x: x + radius, y: y), light, 1.7)
    stroke(.init(x: x, y: y - radius), .init(x: x, y: y + radius), light, 1.7)
  }
  switch cue.path {
  case "glow", "blush":
    mark(132 + 2 * s, 146 + 3 * c, cue.path == "blush" ? 14 : 20, 4 * s, 0.55 + 0.4 * rise)
    if cue.path == "blush" { mark(66, 140, 10, -12, 0.55 * rise) }
  case "hand", "table", "write", "scrub", "fan", "thread", "bowstring", "pet":
    let g = cue.path
    let propX = g == "table" ? 119 : g == "write" || g == "scrub" ? 122 + 10 * s : 122 + 4 * c
    let propY =
      g == "table"
      ? 56 + 2 * c : g == "pet" ? 56 + 5 * rise : g == "scrub" ? 65 : g == "fan" ? 117 : 96 + 5 * s
    let angle =
      g == "fan" ? s * 32 : g == "bowstring" ? -28 + 8 * s : g == "write" ? 8 * s - 12 : s * 7
    mark(propX, propY, g == "pet" ? 34 : 27, angle)
    if g == "write" { stroke(.init(x: 117, y: 83), .init(x: 117 + 17 * t, y: 83 + 2 * s), ink) }
    if g == "thread" {
      let thread = NSBezierPath()
      thread.move(to: .init(x: 116, y: 91))
      thread.curve(
        to: .init(x: 146, y: 86), controlPoint1: .init(x: 124, y: 64 + 6 * s),
        controlPoint2: .init(x: 139, y: 76))
      ink.setStroke()
      thread.stroke()
    }
    if g == "bowstring" { glyph("♪", 139, 124 + 18 * t, 12, 10, 1 - t) }
  case "drift", "trail", "fly", "floatAway", "lift":
    switch cue.path {
    case "lift": mark(127 + 12 * s, 85 + 100 * t, 21 + 9 * t, 4 * s, 1 - 0.65 * t)
    case "floatAway":
      mark(110 + 61 * t, 36 + 5 * s, 26 - 10 * t, s * 6)
      stroke(.init(x: 97 + 61 * t, y: 25 + 4 * s), .init(x: 112 + 61 * t, y: 25 + 5 * s), ink, 1)
    case "fly": mark(82 + 79 * t, 93 + 81 * rise, 24, 18 * c)
    case "trail":
      for i in 0..<3 {
        let q = (t + Double(i) / 3).truncatingRemainder(dividingBy: 1)
        mark(112 + 53 * q, 44 + 18 * sin(pi * q), 11 - 5 * q, 28 * q, 1 - q)
      }
    default: mark(68 + 79 * t, 147 + 26 * sin(phase), 18, s * 19, 0.5 + 0.45 * rise)
    }
  case "rising", "fall", "spray":
    for i in 0..<3 {
      let q = (t + Double(i) / 3).truncatingRemainder(dividingBy: 1)
      if cue.path == "rising" {
        mark(124 + 13 * sin(q * 4.5), 111 + 62 * q, 13 + 6 * q, 8 * s, 1 - q)
      } else if cue.path == "fall" {
        mark(25 + Double(i) * 53 + 16 * sin(q * 4), 184 - 141 * q, 13 + 7 * rise, 110 * q, 0.85)
      } else {
        mark(110 + 69 * q, 102 + 36 * sin(q * pi) - 26 * q, 13 - 7 * q, -60 * q, 1 - q)
      }
    }
  case "catch", "kick", "juggle":
    let n = cue.path == "juggle" ? 3 : 1
    for i in 0..<n {
      let q = (t + Double(i) / Double(n)).truncatingRemainder(dividingBy: 1)
      let base = cue.path == "kick" ? 36.0 : 90.0
      let ax = cue.path == "kick" ? 131.0 : 97.0
      mark(ax + 30 * cos(q * pi), base + 74 * abs(sin(q * pi)), n == 1 ? 22 : 14, 45 * s)
    }
  case "orbit", "ring", "cards":
    let n = cue.path == "cards" ? 4 : 3
    for i in 0..<n {
      let a = phase + Double(i) * 2 * pi / Double(n)
      mark(
        97 + 51 * cos(a), 108 + 22 * sin(a), 15 + 2 * sin(a), cue.path == "cards" ? 24 * sin(a) : 0,
        0.8)
    }
    if cue.path == "ring" {
      let ring = NSBezierPath(ovalIn: NSRect(x: 34, y: 83, width: 127, height: 45))
      ink.withAlphaComponent(0.38 * rise).setStroke()
      ring.lineWidth = 2
      ring.stroke()
    }
  case "spin", "roll", "board":
    if cue.path == "board" {
      let edge = NSRect(x: 115, y: 37, width: 45, height: 23)
      light.withAlphaComponent(0.6).setFill()
      edge.fill()
      for i in 0...4 {
        stroke(
          .init(x: 116 + Double(i) * 10, y: 38), .init(x: 116 + Double(i) * 10, y: 60), ink, 0.6)
        stroke(.init(x: 116, y: 38 + Double(i) * 5), .init(x: 158, y: 38 + Double(i) * 5), ink, 0.6)
      }
      mark(124 + 9 * floor(t * 4), 55 + 23 * (1 - rise), 10)
    } else {
      mark(
        cue.path == "roll" ? 128 + 32 * s : x, cue.path == "roll" ? 38 : y, 28,
        cue.path == "roll" ? 10 * s : 180 * s)
    }
  case "kite", "swing":
    let end = CGPoint(
      x: cue.path == "kite" ? 138 + 29 * s : 98 + 37 * s,
      y: cue.path == "kite" ? 157 + 12 * c : 39 + 8 * abs(s))
    if cue.path == "kite" {
      stroke(.init(x: 119, y: 94), end, ink, 1)
      mark(end.x, end.y, 32, -16 * s)
    } else {
      stroke(.init(x: 66, y: 202), .init(x: end.x - 22, y: end.y), ink, 1.1)
      stroke(.init(x: 132, y: 202), .init(x: end.x + 22, y: end.y), ink, 1.1)
      stroke(.init(x: end.x - 23, y: end.y), .init(x: end.x + 23, y: end.y), light, 3)
      mark(end.x + 23, end.y + 5, 16)
    }
  case "grow", "inflate", "unwrap":
    let f = min(1, t * 1.7)
    mark(123, 83 + 16 * f, 10 + 23 * f, 8 * s)
    if cue.path == "unwrap" { glyph("🎀", 128 + 20 * t, 93 + 42 * rise, 14, 35 * t, 1 - t) }
    if cue.path == "inflate" { stroke(.init(x: 122, y: 75 + 11 * f), .init(x: 116, y: 65), ink, 1) }
  case "bite", "steam", "melt", "dip", "moon":
    let mouth = pow(max(0, sin(pi * t)), 3)
    if cue.path == "bite" || cue.path == "moon" {
      mark(129 - 22 * mouth, 82 + 46 * mouth, 26 - 6 * mouth, -18 * mouth)
      if cue.path == "moon" { glyph("🌙", 41, 177, 23, -10) }
    } else if cue.path == "steam" {
      mark(125, 74, 29)
      for k in 0..<2 {
        let q = (t + Double(k) * 0.5).truncatingRemainder(dividingBy: 1)
        glyph("∿", 122 + 6 * sin(q * pi), 88 + 28 * q, 13, 85, 1 - q)
      }
    } else if cue.path == "dip" {
      glyph("🥣", 126, 65, 31)
      mark(128 + 3 * s, 87 + 16 * c, 18, 12 * s)
    } else {
      mark(123, 92, 28 - 5 * t)
      glyph("💧", 123, 81 - 35 * t, 10, 0, 1 - t)
    }
  case "burst", "spark":
    if cue.path == "spark" {
      mark(139, 75, 35)
      glint(139, 97 + 6 * s, 4 + 4 * rise)
    } else {
      for i in 0..<8 {
        let a = Double(i) * pi / 4
        let q = (t * 1.6).truncatingRemainder(dividingBy: 1)
        let cx = 129 + 32 * q * cos(a)
        let cy = 147 + 32 * q * sin(a) - 9 * q * q
        stroke(
          .init(x: cx - 6 * cos(a), y: cy - 6 * sin(a)), .init(x: cx, y: cy),
          i % 2 == 0 ? light : ink, 2 * (1 - q) + 0.6)
      }
      mark(129, 147, 12 + 4 * rise, 15 * s, 1 - 0.7 * rise)
    }
  case "lantern":
    mark(127 + 9 * s, 75 - 2 * c, 31, 13 * s)
    glint(146 + 9 * s, 77, 2 + 3 * rise)
  default: preconditionFailure("unknown prop path " + cue.path)
  }
}
func paintBody(_ cue: Score, _ image: CGImage, _ t: Double) {
  let a = 2 * pi * t
  let w = sin(a)
  let b = sin(pi * t)
  let fast = sin(a * 2)
  var x = 0.0
  var y = 0.0
  var sx = 1.0
  var sy = 1.0
  var tilt = 0.0
  switch cue.motion {
  case "breathe": sy += 0.025 * b
  case "turn":
    sx = 0.72 + 0.28 * abs(cos(a))
    x = 4 * w
    tilt = 3 * w
  case "step":
    x = 11 * w
    y = 3 * abs(fast)
    tilt = 4 * w
  case "run":
    x = 16 * w
    y = 6 * abs(fast)
    tilt = 8 * cos(a)
  case "float":
    y = 9 + 8 * w
    tilt = 4 * w
  case "sway":
    tilt = 8 * w
    x = 3 * w
  case "stretch":
    sy += 0.075 * b
    sx -= 0.035 * b
    y = 3 * b
  case "tap":
    tilt = 4 * fast
    y = 2 * abs(fast)
  case "crouch":
    sy -= 0.18 * b
    sx += 0.04 * b
    tilt = -4 * b
  case "bow":
    tilt = -11 * b
    sy -= 0.1 * b
  case "nap":
    tilt = -9 - 2 * w
    sy = 0.88 + 0.02 * w
  case "leap":
    y = 19 * b
    sy += 0.035 * b
  case "peek":
    x = 6 * w
    tilt = -9 * b
    sy -= 0.07 * b
  case "kick":
    tilt = -12 * max(0, w)
    y = 6 * abs(w)
  case "wake":
    sy = 0.87 + 0.16 * b
    tilt = -10 + 12 * b
  case "tilt": tilt = 6 * w
  case "shake":
    x = 4 * sin(3 * a)
    tilt = 5 * fast
  case "waltz":
    x = 14 * w
    y = 5 * abs(w)
    tilt = 10 * w
    sx = 0.87 + 0.13 * cos(a)
  case "dance":
    tilt = 10 * w
    y = 11 * abs(fast)
    x = 6 * w
  case "rock":
    x = 17 * w
    tilt = 9 * w
    y = 3 + 5 * abs(w)
  default: preconditionFailure("unknown motion " + cue.motion)
  }
  NSGraphicsContext.saveGraphicsState()
  defer { NSGraphicsContext.restoreGraphicsState() }
  let tr = NSAffineTransform()
  tr.translateX(by: 96 + x, yBy: 96 + y)
  tr.rotate(byDegrees: tilt)
  tr.scaleX(by: sx, yBy: sy)
  tr.translateX(by: -96, yBy: -96)
  tr.concat()
  NSImage(cgImage: image, size: .zero).draw(
    in: NSRect(x: 8, y: 6, width: 176, height: 191), from: .zero, operation: .sourceOver,
    fraction: 1)
}
struct Spec: Codable { let file: String, frames: Int, fps: Double, weight: Int, group: String }
struct Library: Codable {
  var clips = [String: Spec]()
  var idle = [String](), bedtime = [String](), sleep = [String](), waking = [String]()
}
let args = CommandLine.arguments
guard args.count == 4 else { exit(2) }
let sheet = URL(fileURLWithPath: args[1])
let config = URL(fileURLWithPath: args[2])
let output = URL(fileURLWithPath: args[3])
let scores = try JSONDecoder().decode([Score].self, from: Data(contentsOf: config))
guard let source = CGImageSourceCreateWithURL(sheet as CFURL, nil),
  let atlas = CGImageSourceCreateImageAtIndex(source, 0, nil), atlas.width == 1536,
  atlas.height >= 1872
else { exit(3) }
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let rows = counts.enumerated().map { r, n in
  (0..<n).map { i in
    atlas.cropping(to: CGRect(x: i * width, y: r * height, width: width, height: height))!
  }
}
let space = CGColorSpace(name: CGColorSpace.sRGB)!
var book = Library()
for score in scores {
  try autoreleasepool {
    guard let targetRow = names.firstIndex(of: score.pose),
      let ctx = CGContext(
        data: nil, width: width * frameCount, height: height, bitsPerComponent: 8, bytesPerRow: 0,
        space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { throw CocoaError(.fileWriteUnknown) }
    let gc = NSGraphicsContext(cgContext: ctx, flipped: false)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = gc
    defer { NSGraphicsContext.restoreGraphicsState() }
    for i in 0..<frameCount {
      ctx.saveGState()
      ctx.translateBy(x: CGFloat(i * width), y: 0)
      ctx.clip(to: CGRect(x: 0, y: 0, width: width, height: height))
      let t = Double(i) / Double(frameCount - 1)
      // A few beats begin at rest and change expression only at their accented beat.
      let r = (score.motion == "wake" && i < 3 || score.motion == "peek" && i < 2) ? 6 : targetRow
      let frame = rows[r][i * rows[r].count / frameCount % rows[r].count]
      let behind = ["fall", "kite", "swing", "moon", "ring", "fly"].contains(score.path)
      if behind { paintProp(score, t) }
      paintBody(score, frame, t)
      if !behind { paintProp(score, t) }
      ctx.restoreGState()
    }
    let file = score.id + ".png"
    let url = output.appendingPathComponent(file)
    guard let result = ctx.makeImage(),
      let encoder = CGImageDestinationCreateWithURL(
        url as CFURL, UTType.png.identifier as CFString, 1, nil)
    else { throw CocoaError(.fileWriteUnknown) }
    CGImageDestinationAddImage(encoder, result, nil)
    guard CGImageDestinationFinalize(encoder) else { throw CocoaError(.fileWriteUnknown) }
    book.clips[score.title] = Spec(
      file: file, frames: frameCount, fps: 8, weight: 1, group: score.group)
    if ["生活", "玩耍", "节令"].contains(score.group) { book.idle.append(score.title) }
    if score.id == "shuijiao-kaishi" { book.bedtime = [score.title] }
    if score.id == "shuijiao-xunhuan" { book.sleep = [score.title] }
    if score.id == "shuijiao-qilai" { book.waking = [score.title] }
  }
}
let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
try encoder.encode(book).write(to: output.appendingPathComponent("pet-plus.json"), options: .atomic)
print("Cartethyia: \(book.clips.count) local clips, \(book.clips.count*frameCount) frames")
