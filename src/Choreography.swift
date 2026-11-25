import AppKit

// All paths and particles below are drawn locally over the user's own frames.
enum PetScene: String, CaseIterable {
  case rain = "听雨"
  case snow = "初雪"
  case petals = "花瓣起舞"
  case leaves = "拾秋叶"
  case moon = "月下守望"
  case sun = "迎接晨光"
  case ward = "祈愿水环"
  case cascade = "细雨成瀑"
  case tide = "潮声回旋"
  case feather = "风中羽翼"
  case comet = "追逐流星"
  case constellation = "描画星座"
  case letter = "拆开来信"
  case music = "轻轻哼歌"
  case map = "查看旅图"
  case lamp = "提灯夜行"
  case book = "记下见闻"
  case gift = "送出礼物"
  case cake = "分享蛋糕"
  case berry = "采摘草莓"
  case honey = "品尝蜂蜜"
  case soup = "捧一碗热汤"
  case apple = "午后苹果"
  case cookie = "烤小饼干"
  case plenty = "星囊充盈"
  case bright = "星囊闪耀"
  case half = "细数星砂"
  case little = "收好余星"
  case last = "仅余星火"
  case empty = "星囊见底"
  var group: String {
    let i = Self.allCases.firstIndex(of: self)! / 6
    return ["四季", "风与潮", "旅途", "茶点", "额度"][i]
  }
  var motif: String {
    switch self {
    case .rain: return "drop"
    case .snow: return "snowflake"
    case .petals: return "camera.macro"
    case .leaves: return "leaf.fill"
    case .moon: return "moon.stars.fill"
    case .sun: return "sunrise.fill"
    case .ward: return "drop.circle"
    case .cascade: return "drop.fill"
    case .tide: return "water.waves"
    case .feather: return "feather.fill"
    case .comet: return "sparkle"
    case .constellation: return "sparkles"
    case .letter: return "envelope.open.fill"
    case .music: return "music.note"
    case .map: return "map.fill"
    case .lamp: return "lamp.lantern.fill"
    case .book: return "book.pages.fill"
    case .gift: return "gift.fill"
    case .cake: return "birthday.cake.fill"
    case .berry: return "leaf.circle"
    case .honey: return "hexagon.fill"
    case .soup: return "cup.and.saucer"
    case .apple: return "apple.logo"
    case .cookie: return "circle.grid.2x2.fill"
    default: return "star.fill"
    }
  }
  var pose: String {
    switch group {
    case "四季": return "waving"
    case "风与潮": return "jumping"
    case "额度": return self == .empty ? "failed" : self == .last ? "waiting" : "review"
    case "茶点": return "waiting"
    default: return "review"
    }
  }
  func paint(_ rect: NSRect, elapsed: Double) {
    let i = Self.allCases.firstIndex(of: self)!
    let j = i % 6
    let t = min(1, max(0, elapsed / 3.4))
    let alpha = min(1, min(t * 10, (1 - t) * 9))
    let color = [
      NSColor.systemTeal, .systemMint, .systemPink, .systemOrange, .systemIndigo, .systemYellow,
    ][j]
    let conf = NSImage.SymbolConfiguration(paletteColors: [color, .systemOrange])
    guard
      let icon = NSImage(systemSymbolName: motif, accessibilityDescription: nil)?
        .withSymbolConfiguration(conf)
    else { return }
    let n = group == "额度" ? 6 - j : group == "旅途" || group == "茶点" ? 1 : 6
    for k in 0..<n {
      let phase = Double(k) / Double(n)
      let theta = (phase + t * (0.9 + Double(j) * 0.12)) * 2 * Double.pi
      var x = 0.62 + 0.14 * cos(theta)
      var y = 0.49 + 0.12 * sin(theta)
      var w = rect.width * 0.24
      if group == "四季" {
        x = (phase + 0.12 * sin(theta) + 1).truncatingRemainder(dividingBy: 1)
        y = 1 - (t * 1.2 + phase).truncatingRemainder(dividingBy: 1)
        w *= 0.45
      }
      if group == "风与潮" || group == "额度" {
        x = 0.5 + 0.40 * cos(theta)
        y = 0.52 + 0.26 * sin(theta)
        w *= 0.54
      }
      icon.draw(
        in: NSRect(x: rect.width * x - w / 2, y: rect.height * y - w / 2, width: w, height: w),
        from: .zero, operation: .sourceOver, fraction: alpha)
    }
  }
}
extension Sprite {
  func playScene(_ scene: PetScene) {
    activeScene = scene
    effect = nil
    effectStart = ProcessInfo.processInfo.systemUptime
    effectEnd = effectStart + 3.4
    host?.act(scene.pose)
    host?.overrideUntil = effectEnd
    needsDisplay = true
  }
}
