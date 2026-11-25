import AppKit

// Render from the high-resolution transparent crop of the user's existing character.
let portrait = NSImage(contentsOfFile: CommandLine.arguments[1])!
let directory = URL(fileURLWithPath: CommandLine.arguments[2])
let tile = NSRect(x: 64, y: 64, width: 896, height: 896)
func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> NSColor {
  NSColor(srgbRed: r, green: g, blue: b, alpha: 1)
}
func star(_ x: CGFloat, _ y: CGFloat, _ size: CGFloat) {
  let p = NSBezierPath()
  for i in 0..<8 {
    let a = CGFloat(i) * .pi / 4
    let r = i % 2 == 0 ? size : size * 0.26
    let point = NSPoint(x: x + cos(a)*r, y: y + sin(a)*r*1.18)
    if i == 0 { p.move(to: point) } else { p.line(to: point) }
  }
  p.close(); p.fill()
}
for logical in [16,32,128,256,512] {
  for scale in [1,2] {
    let n = logical * scale
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: n, pixelsHigh: n, bitsPerSample: 8,
      samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.current = context
    context.imageInterpolation = .high
    context.cgContext.scaleBy(x: CGFloat(n)/1024, y: CGFloat(n)/1024)
    let shape = NSBezierPath(roundedRect: tile, xRadius: 205, yRadius: 205)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowOffset = NSSize(width: 0, height: -11)
    shadow.shadowBlurRadius = 19
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.32)
    shadow.set()
    color(0.21,0.38,0.38).setFill(); shape.fill()
    NSGraphicsContext.restoreGraphicsState()
    shape.addClip()
    NSGradient(colors: [color(0.15,0.31,0.33),color(0.30,0.51,0.48),color(0.66,0.77,0.66)])!.draw(in: tile, angle: 70)
    color(0.72,0.81,0.68).withAlphaComponent(0.6).setFill()
    NSBezierPath(ovalIn: NSRect(x: 129,y: 151,width: 766,height: 746)).fill()
    color(0.96,0.86,0.61).setStroke()
    let ring = NSBezierPath(ovalIn: NSRect(x: 105,y: 129,width: 814,height: 789))
    ring.lineWidth = 5; ring.stroke()
    // A close crop keeps the face legible at Finder's smallest icon size.
    portrait.draw(in: NSRect(x: 61,y: -112,width: 902,height: 1020))
    color(1,0.90,0.67).setFill()
    star(169,698,36); star(849,569,38); star(802,771,15)
    let rim = NSBezierPath(roundedRect: tile.insetBy(dx: 7,dy: 7),xRadius: 200,yRadius: 200)
    rim.lineWidth = 10; NSColor.white.withAlphaComponent(0.4).setStroke(); rim.stroke()
    NSGraphicsContext.restoreGraphicsState()
    let name = "icon_\(logical)x\(logical)" + (scale == 2 ? "@2x" : "") + ".png"
    try bitmap.representation(using: .png, properties: [:])!.write(to: directory.appendingPathComponent(name))
  }
}
