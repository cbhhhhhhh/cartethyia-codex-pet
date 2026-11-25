import AppKit
import SwiftUI

// Keep the field editor attached to the floating panel when another app was frontmost.
struct PetInput: NSViewRepresentable {
  @Binding var text: String
  let submit: () -> Void
  func makeCoordinator() -> Coordinator { Coordinator(self) }
  final class Coordinator: NSObject, NSTextFieldDelegate {
    var owner: PetInput
    init(_ owner: PetInput) { self.owner = owner }
    func controlTextDidChange(_ notification: Notification) {
      if let field = notification.object as? NSTextField { owner.text = field.stringValue }
    }
    @objc func enter(_ field: NSTextField) {
      owner.text = field.stringValue
      owner.submit()
    }
  }
  final class Field: NSTextField {
    override func viewDidMoveToWindow() {
      super.viewDidMoveToWindow()
      DispatchQueue.main.async { [weak self] in
        guard let self = self, let w = self.window else { return }
        w.makeFirstResponder(self)
      }
    }
  }
  func makeNSView(context: Context) -> NSTextField {
    let f = Field()
    f.placeholderString = "和卡提聊聊…"
    f.isBezeled = false
    f.drawsBackground = false
    f.font = NSFont(name: PetLettering.face, size: 16) ?? .systemFont(ofSize: 16)
    f.delegate = context.coordinator
    f.target = context.coordinator
    f.action = #selector(Coordinator.enter(_:))
    f.cell?.sendsActionOnEndEditing = false
    f.setAccessibilityLabel("和卡提聊聊")
    return f
  }
  func updateNSView(_ f: NSTextField, context: Context) {
    context.coordinator.owner = self
    if f.stringValue != text { f.stringValue = text }
  }
}
