import AppKit
import SwiftUI

struct ChatPair: Codable, Identifiable {
  let id: String, user: String, assistant: String
  var action: String?, emotion: String?, image: String?, art: [String]?, spriteArt: Bool?,
    pack: String?, picture: String?, clip: String?
}

struct PairArt: View {
  let pair: ChatPair, host: Host
  var body: some View {
    HStack {
      ForEach(pair.art ?? [], id: \.self) { path in
        if let image = NSImage(contentsOfFile: path) {
          Button {
            NSWorkspace.shared.open(URL(fileURLWithPath: path))
          } label: {
            Image(nsImage: image).resizable().scaledToFit().frame(maxWidth: 65, maxHeight: 55)
          }.buttonStyle(.plain)
        }
      }
      if pair.spriteArt == true, let row = names.firstIndex(of: pair.action ?? ""),
        host.sprite.frames.indices.contains(row), let frame = host.sprite.frames[row].first
      {
        Image(nsImage: frame).resizable().scaledToFit().frame(height: 52).accessibilityLabel(
          "卡提的表情")
      }
    }
  }
}
final class HistoryEdits: ObservableObject {
  @Published var selected = Set<String>()
  @Published var confirmClear = false
}
struct ChatView: View {
  @ObservedObject var state: CompanionState
  let host: Host
  @ObservedObject var edits: HistoryEdits
  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Text("聊天记录").font(.headline)
        Spacer()
        Button("删除选中") {
          host.send(["op": "history-delete", "ids": Array(edits.selected)])
          edits.selected.removeAll()
        }.disabled(edits.selected.isEmpty)
        Button("清空…") { edits.confirmClear = true }.disabled(state.pairs.isEmpty)
      }
      ScrollView {
        LazyVStack(alignment: .leading, spacing: 12) {
          if state.pairs.isEmpty { Text("还没有已完成的对话。").foregroundStyle(.secondary) }
          ForEach(Array(state.pairs.enumerated()), id: \.element.id) { idx, pair in
            if state.config.rounds > 0 && idx == max(0, state.pairs.count - state.config.rounds) {
              Text("以下对话进入最近 \(state.config.rounds) 轮记忆").font(.caption).foregroundStyle(.secondary)
              Divider()
            }
            HStack(alignment: .top) {
              Toggle(
                "选择",
                isOn: Binding(
                  get: { edits.selected.contains(pair.id) },
                  set: {
                    if $0 { edits.selected.insert(pair.id) } else { edits.selected.remove(pair.id) }
                  })
              ).labelsHidden().toggleStyle(.checkbox)
              VStack(alignment: .leading, spacing: 5) {
                Text("你　" + pair.user).textSelection(.enabled)
                if let path = pair.image, let img = NSImage(contentsOfFile: path) {
                  Button {
                    NSWorkspace.shared.open(URL(fileURLWithPath: path))
                  } label: {
                    Image(nsImage: img).resizable().scaledToFit().frame(maxHeight: 76)
                  }.buttonStyle(.plain)
                }
                Text("卡提　" + pair.assistant).textSelection(.enabled)
                PairArt(pair: pair, host: host)
              }
              Spacer()
              Button {
                host.readAloud(pair.assistant)
              } label: {
                Image(systemName: "speaker.wave.2")
              }.buttonStyle(.plain).help("朗读这句话")
            }
          }
        }.frame(maxWidth: .infinity, alignment: .leading)
      }
      Divider()
      HStack {
        Text("模型上下文　\(state.config.rounds) 轮").font(.caption)
        Spacer()
        Button("和卡提说话") { host.showChat() }
      }
    }.padding().frame(minWidth: 410, minHeight: 320)
      .alert("清空这个角色的全部聊天记录？", isPresented: $edits.confirmClear) {
        Button("取消", role: .cancel) {}
        Button("清空", role: .destructive) {
          edits.selected.removeAll()
          host.clearChat()
        }
      }
  }
}
