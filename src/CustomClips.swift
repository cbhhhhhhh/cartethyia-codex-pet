import AppKit
import ImageIO
import QuartzCore

// Optional per-pack image sequences. Resolve every file under the selected pet's directory.
struct ClipSpec: Decodable {
  let file: String, frames: Int
  let fps: Double?
  let weight: Int?
  let group: String?
  let travel: String?
}
struct ClipLibrary: Decodable {
  let clips: [String: ClipSpec]
  let idle: [String]?
  let sleep: [String]?
  let waking: [String]?
  let bedtime: [String]?
}
struct ClipPlayer {
  let key: String, frames: [NSImage], atlas: CGImage, mask: NSBitmapImageRep, fps: Double, start: Double
  var frame: Int { Int(max(0, ProcessInfo.processInfo.systemUptime - start) * fps) % frames.count }
}
extension Sprite {
  func refreshClipLayer(visible: Bool) {
    CATransaction.begin()
    CATransaction.setDisableActions(true)
    defer { CATransaction.commit() }
    clipLayer.removeAnimation(forKey: "frames")
    guard visible, let clip = activeClip else {
      clipLayer.contents = nil
      clipLayer.removeFromSuperlayer()
      needsDisplay = true
      return
    }
    wantsLayer = true
    guard let backing = layer else { return }
    if clipLayer.superlayer !== backing { backing.addSublayer(clipLayer) }
    clipLayer.frame = bounds
    clipLayer.contents = clip.atlas
    clipLayer.contentsGravity = .resize
    let count = clip.frames.count
    let cells = (0..<count).map { NSValue(rect:NSRect(x:Double($0)/Double(count), y:0, width:1/Double(count), height:1)) }
    clipLayer.contentsRect = cells[clip.frame].rectValue
    let timeline = CAKeyframeAnimation(keyPath: "contentsRect")
    timeline.values = cells
    timeline.keyTimes = (0..<count).map { NSNumber(value: Double($0)/Double(count)) }
    timeline.calculationMode = .discrete
    timeline.duration = Double(count)/clip.fps
    timeline.timeOffset = (ProcessInfo.processInfo.systemUptime-clip.start).truncatingRemainder(dividingBy: timeline.duration)
    timeline.repeatCount = .infinity
    clipLayer.add(timeline, forKey: "frames")
    lastPoseRect = bounds
    lastPoseTransform = .identity
    needsDisplay = true
  }
  func loadClipLibrary(_ root: URL) {
    let privateArt = support.appendingPathComponent(
      "appearance/" + root.lastPathComponent + "/current"
    ).resolvingSymlinksInPath()
    let assets = [root, shippedPacks.appendingPathComponent(root.lastPathComponent), privateArt]
      .first { FileManager.default.fileExists(atPath: $0.appendingPathComponent("pet-plus.json").path) } ?? root
    clipRoot = assets
    activeClip = nil
    guard let d = try? Data(contentsOf: assets.appendingPathComponent("pet-plus.json")),
      d.count < 512 * 1024
    else {
      clipLibrary = nil
      return
    }
    clipLibrary = try? JSONDecoder().decode(ClipLibrary.self, from: d)
  }
  @discardableResult func playClip(_ key: String, loop: Bool = false) -> Bool {
    guard let root = clipRoot, let spec = clipLibrary?.clips[key], (1...48).contains(spec.frames)
    else { return false }
    let path = root.appendingPathComponent(spec.file).resolvingSymlinksInPath()
    guard path.path.hasPrefix(root.resolvingSymlinksInPath().path + "/"),
      let source = CGImageSourceCreateWithURL(path as CFURL, nil),
      let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
      let w = props[kCGImagePropertyPixelWidth] as? Int,
      let h = props[kCGImagePropertyPixelHeight] as? Int,
      h > 0, h <= 512, w > 0, w % spec.frames == 0, w / spec.frames <= 512, w * h <= 8_388_608,
      let cg = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary)
    else { return false }
    var images = [NSImage]()
    let mask = NSBitmapImageRep(cgImage: cg)
    for i in 0..<spec.frames {
      guard
        let c = cg.cropping(
          to: CGRect(x: i * w / spec.frames, y: 0, width: w / spec.frames, height: h))
      else { return false }
      images.append(NSImage(cgImage: c, size: .zero))
    }
    let fps = max(1, min(30, spec.fps ?? 8))
    let now = ProcessInfo.processInfo.systemUptime
    activeClip = ClipPlayer(key: key, frames: images, atlas: cg, mask: mask, fps: fps, start: now)
    effect = nil
    activeScene = nil
    effectEnd = 0
    host?.overrideUntil = loop ? .greatestFiniteMagnitude : now + Double(spec.frames) / fps
    needsDisplay = true
    return true
  }
  func pickClip(_ pool: [String]?) -> String? {
    let candidates = (pool ?? []).prefix(256).filter { clipLibrary?.clips[$0] != nil }
    let weighted = candidates.flatMap { k in
      Array(repeating: k, count: min(16, max(1, clipLibrary?.clips[k]?.weight ?? 1)))
    }
    return weighted.randomElement()
  }
}
