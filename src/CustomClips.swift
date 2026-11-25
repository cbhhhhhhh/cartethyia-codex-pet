import AppKit
import ImageIO

// Optional per-pack image sequences. Resolve every file under the selected pet's directory.
struct ClipSpec: Decodable {
  let file: String, frames: Int
  let fps: Double?
  let weight: Int?
  let group: String?
}
struct ClipLibrary: Decodable {
  let clips: [String: ClipSpec]
  let idle: [String]?
  let sleep: [String]?
  let waking: [String]?
  let bedtime: [String]?
}
struct ClipPlayer {
  let key: String, frames: [NSImage], masks: [NSBitmapImageRep], fps: Double, start: Double
  var frame: Int { Int(max(0, ProcessInfo.processInfo.systemUptime - start) * fps) % frames.count }
}
extension Sprite {
  func refreshClipTimer() {
    clipTimer?.invalidate()
    clipTimer = nil
    guard let clip = activeClip, let window = window, window.isVisible else { return }
    clipTimer = Timer.scheduledTimer(withTimeInterval: 1 / clip.fps, repeats: true) {
      [weak self] _ in self?.needsDisplay = true
    }
  }
  func loadClipLibrary(_ root: URL) {
    let privateArt = support.appendingPathComponent(
      "appearance/" + root.lastPathComponent + "/current"
    ).resolvingSymlinksInPath()
    let assets = [root, privateArt, shippedPacks.appendingPathComponent(root.lastPathComponent)]
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
      let cg = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else { return false }
    var images = [NSImage]()
    var masks = [NSBitmapImageRep]()
    for i in 0..<spec.frames {
      guard
        let c = cg.cropping(
          to: CGRect(x: i * w / spec.frames, y: 0, width: w / spec.frames, height: h))
      else { return false }
      images.append(NSImage(cgImage: c, size: .zero))
      masks.append(NSBitmapImageRep(cgImage: c))
    }
    let fps = max(1, min(30, spec.fps ?? 8))
    let now = ProcessInfo.processInfo.systemUptime
    activeClip = ClipPlayer(key: key, frames: images, masks: masks, fps: fps, start: now)
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
