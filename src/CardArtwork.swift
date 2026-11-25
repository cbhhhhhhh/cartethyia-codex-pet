import AppKit
import SwiftUI

enum CardMood: String {
  case calm, happy, curious, focused, sad
  var row: Int {
    switch self {
    case .calm: return 0
    case .happy: return 3
    case .curious: return 6
    case .focused: return 8
    case .sad: return 5
    }
  }
  var wash: Color {
    switch self {
    case .happy: return Color(red: 0.99, green: 0.88, blue: 0.81)
    case .curious: return Color(red: 0.93, green: 0.88, blue: 0.97)
    case .focused: return Color(red: 0.83, green: 0.91, blue: 0.91)
    case .sad: return Color(red: 0.86, green: 0.90, blue: 0.96)
    case .calm: return Color(red: 0.89, green: 0.93, blue: 0.83)
    }
  }
  init(emotion: String, action: String = "") {
    if let mood = Self(rawValue: emotion) { self = mood; return }
    switch action {
    case "jumping", "waving": self = .happy
    case "failed": self = .sad
    case "running", "review": self = .focused
    case "waiting": self = .curious
    default: self = .calm
    }
  }
  init(status: String) {
    switch status {
    case "success": self = .happy
    case "waiting-for-approval", "thinking": self = .curious
    case "review", "working": self = .focused
    case "timeout", "error": self = .sad
    default: self = .calm
    }
  }
  var gestures: [String] {
    switch self {
    case .happy: return ["见到你开心一跳", "没忍住笑出声", "举高小手问好", "转一圈给你看"]
    case .curious: return ["让我再想一想", "托着腮想起一句话", "侧耳听风"]
    case .focused: return ["写下旅途一笔", "让我再想一想", "把完成的记录归档"]
    case .sad: return ["轻轻别过脸", "垂下眼睛轻轻叹气", "托着腮想起一句话"]
    case .calm: return ["提裙行骑士礼", "今天一起吃什么", "小声哼一支歌", "在围巾边比对新丝带"]
    }
  }
}

let cardInk = Color(red: 0.24, green: 0.21, blue: 0.22)
let cardPine = Color(red: 0.27, green: 0.39, blue: 0.35)
let paper = Color(red: 0.997, green: 0.987, blue: 0.958)
enum PetLettering {
  static let face = ["DFWaWaSC-W5", "STYuanti-SC-Bold", "PingFangSC-Semibold"].first {
    NSFont(name: $0, size: 16) != nil
  } ?? NSFont.systemFont(ofSize: 16).fontName
  static func title(_ size: CGFloat) -> Font { .custom(face, fixedSize: size) }
}

struct PaperBubble: Shape {
  let tipAtTop: Bool
  let tipX: CGFloat
  func path(in r: CGRect) -> Path {
    let tail: CGFloat = 10
    let box = CGRect(x: r.minX, y: r.minY + (tipAtTop ? tail : 0),
                     width: r.width, height: r.height-tail)
    let x = max(25,min(r.width-25,tipX)), y = tipAtTop ? box.minY : box.maxY
    let direction: CGFloat = tipAtTop ? -1 : 1
    // One continuous outline avoids a seam between the point and the paper.
    let rr: CGFloat = 18
    var p = Path()
    p.move(to: CGPoint(x: box.minX+rr,y: box.minY))
    if tipAtTop { pointer(&p,x,y,direction,fromLeft: true) }
    p.addLine(to: CGPoint(x: box.maxX-rr,y: box.minY))
    p.addQuadCurve(to: CGPoint(x: box.maxX,y: box.minY+rr), control: CGPoint(x: box.maxX,y: box.minY))
    p.addLine(to: CGPoint(x: box.maxX,y: box.maxY-rr))
    p.addQuadCurve(to: CGPoint(x: box.maxX-rr,y: box.maxY), control: CGPoint(x: box.maxX,y: box.maxY))
    if !tipAtTop { pointer(&p,x,y,direction,fromLeft: false) }
    p.addLine(to: CGPoint(x: box.minX+rr,y: box.maxY))
    p.addQuadCurve(to: CGPoint(x: box.minX,y: box.maxY-rr), control: CGPoint(x: box.minX,y: box.maxY))
    p.addLine(to: CGPoint(x: box.minX,y: box.minY+rr))
    p.addQuadCurve(to: CGPoint(x: box.minX+rr,y: box.minY), control: CGPoint(x: box.minX,y: box.minY))
    p.closeSubpath()
    return p
  }
  private func pointer(_ p: inout Path, _ x: CGFloat, _ y: CGFloat, _ dy: CGFloat, fromLeft: Bool) {
    let offset: CGFloat = fromLeft ? 10 : -10
    p.addLine(to: CGPoint(x: x-offset,y: y))
    p.addLine(to: CGPoint(x: x,y: y+dy*10))
    p.addLine(to: CGPoint(x: x+offset,y: y))
  }
}

// A cameo made from this character's actual frames, with a tiny foil-and-leaf border.
struct CardPortrait: View {
  let sprite: Sprite
  let mood: CardMood
  let variant: Int
  var large = false
  private static let portraits = NSCache<NSString,NSImage>()
  private var illustration: NSImage? {
    guard sprite.host?.currentPack == "cartethyia" else { return nil }
    let key = "\(mood.rawValue)-\(variant % 2)"
    if let found = Self.portraits.object(forKey:key as NSString) { return found }
    guard let file = Bundle.main.url(forResource:key,withExtension:"png",subdirectory:"web/portraits"),
          let image = NSImage(contentsOf:file) else { return nil }
    Self.portraits.setObject(image,forKey:key as NSString)
    return image
  }
  var body: some View {
    GeometryReader { geo in
      let w = geo.size.width, h = geo.size.height
      ZStack {
        RoundedRectangle(cornerRadius: large ? 17 : 11)
          .fill(LinearGradient(colors: [mood.wash.opacity(0.48), mood.wash], startPoint: .top, endPoint: .bottom))
        Canvas { ctx, size in
          let w=size.width, h=size.height
          let gold=Color(red: 0.70, green: 0.56, blue: 0.32)
          let medallion=CGRect(x: w*0.5-h*0.41, y: h*0.08, width: h*0.82, height: h*0.82)
          ctx.fill(Path(ellipseIn: medallion),with: .color(paper.opacity(0.78)))
          ctx.stroke(Path(ellipseIn: medallion.insetBy(dx: -3,dy: -3)),with:.color(gold.opacity(0.4)),lineWidth:0.8)
          for (x,y,r) in [(0.15,0.30,0.065),(0.79,0.67,0.055),(0.86,0.27,0.03),(0.19,0.71,0.025)] {
            let c = CGPoint(x:x*w,y:y*h)
            var star=Path()
            for i in 0..<8 {
              let a=Double(i)*Double.pi/4
              let arm=h*r*(i.isMultiple(of:2) ? 1 : 0.27)
              let pt=CGPoint(x:c.x+cos(a)*arm,y:c.y+sin(a)*arm*1.3)
              if i==0 { star.move(to:pt) } else { star.addLine(to:pt) }
            }
            star.closeSubpath()
            ctx.fill(star,with:.color(gold.opacity(0.82)))
          }
        }
        if let artwork = illustration {
          Image(nsImage:artwork).resizable().interpolation(.high).aspectRatio(contentMode:.fit)
            .frame(height: h*0.97).frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.bottom)
        } else if sprite.frames.indices.contains(mood.row), !sprite.frames[mood.row].isEmpty {
          let frames = sprite.frames[mood.row]
          Image(nsImage: frames[variant % frames.count]).resizable().interpolation(.high)
            .aspectRatio(contentMode: .fit).frame(width: h*0.96,height: h*0.97)
            .rotationEffect(.degrees(large ? (variant.isMultiple(of: 2) ? -3 : 3) : 0))
            .shadow(color: cardInk.opacity(0.12),radius: 1.2,y: 1.5)
        }
      }.frame(width:w,height:h).clipShape(RoundedRectangle(cornerRadius:large ? 17 : 11))
        .overlay(RoundedRectangle(cornerRadius:large ? 17 : 11).strokeBorder(.white.opacity(0.87),lineWidth:2))
    }.accessibilityHidden(true)
  }
}
