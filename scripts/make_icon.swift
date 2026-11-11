import AppKit
import CoreGraphics

// Draws the app icon on a 1024-point canvas (y grows downward) and exports
// each macOS AppIcon size as PNG into the folder given as first argument.
// Usage: swift scripts/make_icon.swift Conformig2AAF/Assets.xcassets/AppIcon.appiconset

func color(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255, alpha: a)
}

func linear(_ ctx: CGContext, _ colors: [CGColor], from: CGPoint, to: CGPoint) {
    let g = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB),
                       colors: colors as CFArray, locations: nil)!
    ctx.drawLinearGradient(g, start: from, end: to, options: [])
}

func draw(_ ctx: CGContext) {
    let body = CGRect(x: 100, y: 100, width: 824, height: 824)
    let squircle = CGPath(roundedRect: body, cornerWidth: 185, cornerHeight: 185, transform: nil)

    // Drop shadow + background.
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: 12), blur: 24, color: color(0x000000, 0.45))
    ctx.addPath(squircle); ctx.setFillColor(color(0x15173F)); ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(squircle); ctx.clip()
    linear(ctx, [color(0x30357F), color(0x0D0F2C)], from: CGPoint(x: 512, y: 100), to: CGPoint(x: 512, y: 924))

    // Film strip.
    let strip = CGRect(x: 100, y: 230, width: 824, height: 230)
    ctx.setFillColor(color(0x0A0A12)); ctx.fill(strip)
    for i in 0..<12 {
        let x = 118 + CGFloat(i) * 70
        for y in [strip.minY + 16, strip.maxY - 16 - 26] {
            let hole = CGPath(roundedRect: CGRect(x: x, y: y, width: 36, height: 26),
                              cornerWidth: 6, cornerHeight: 6, transform: nil)
            ctx.addPath(hole)
        }
    }
    ctx.setFillColor(color(0xE8E8F0, 0.85)); ctx.fillPath()
    for i in 0..<3 {
        let frame = CGRect(x: 150 + CGFloat(i) * 248, y: strip.minY + 60, width: 228, height: 110)
        ctx.saveGState()
        ctx.addPath(CGPath(roundedRect: frame, cornerWidth: 10, cornerHeight: 10, transform: nil)); ctx.clip()
        linear(ctx, [color(0x5AC8FA), color(0x2F6BD8)], from: CGPoint(x: frame.minX, y: frame.minY),
               to: CGPoint(x: frame.maxX, y: frame.maxY))
        ctx.restoreGState()
    }

    // Waveform bars.
    let centerY: CGFloat = 690
    let bars = 23
    let barW: CGFloat = 18, gap: CGFloat = 10
    let startX = 512 - (CGFloat(bars) * (barW + gap) - gap) / 2
    let heights: [CGFloat] = [0.18, 0.30, 0.22, 0.45, 0.62, 0.40, 0.75, 0.95, 0.70, 0.52, 0.85, 1.0,
                              0.80, 0.58, 0.90, 0.66, 0.48, 0.72, 0.42, 0.30, 0.38, 0.22, 0.14]
    for i in 0..<bars {
        let h = max(heights[i] * 300, barW)
        let r = CGRect(x: startX + CGFloat(i) * (barW + gap), y: centerY - h / 2, width: barW, height: h)
        ctx.addPath(CGPath(roundedRect: r, cornerWidth: barW / 2, cornerHeight: barW / 2, transform: nil))
    }
    ctx.saveGState()
    ctx.clip()
    linear(ctx, [color(0xFFD60A), color(0xFF9F0A)], from: CGPoint(x: 512, y: centerY - 150),
           to: CGPoint(x: 512, y: centerY + 150))
    ctx.restoreGState()

    // Sync line crossing picture and sound.
    ctx.saveGState()
    ctx.setShadow(offset: .zero, blur: 18, color: color(0xFF453A, 0.8))
    ctx.setFillColor(color(0xFF453A))
    ctx.addPath(CGPath(roundedRect: CGRect(x: 503, y: 200, width: 18, height: 660),
                       cornerWidth: 9, cornerHeight: 9, transform: nil))
    ctx.fillPath()
    // Playhead marker.
    ctx.move(to: CGPoint(x: 472, y: 180)); ctx.addLine(to: CGPoint(x: 552, y: 180))
    ctx.addLine(to: CGPoint(x: 512, y: 230)); ctx.closePath(); ctx.fillPath()
    ctx.restoreGState()

    // Subtle top highlight.
    linear(ctx, [color(0xFFFFFF, 0.10), color(0xFFFFFF, 0)], from: CGPoint(x: 512, y: 100), to: CGPoint(x: 512, y: 420))
    ctx.restoreGState()
}

let out = URL(fileURLWithPath: CommandLine.arguments[1])
for px in [16, 32, 64, 128, 256, 512, 1024] {
    let ctx = CGContext(data: nil, width: px, height: px, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    let s = CGFloat(px) / 1024
    ctx.translateBy(x: 0, y: CGFloat(px)); ctx.scaleBy(x: s, y: -s)
    ctx.interpolationQuality = .high
    draw(ctx)
    let rep = NSBitmapImageRep(cgImage: ctx.makeImage()!)
    try! rep.representation(using: .png, properties: [:])!
        .write(to: out.appendingPathComponent("icon_\(px).png"))
}
