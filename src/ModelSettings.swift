import AppKit
import Security
import SwiftUI

struct PetPicture: Codable, Identifiable {
  let id: String, title: String, description: String, file: String
  func thumbnail(size: CGFloat) -> NSImage? {
    guard let image = NSImage(contentsOfFile: file) else { return nil }
    let factor = size / max(image.size.width, image.size.height, 1)
    image.size = NSSize(width: image.size.width * factor, height: image.size.height * factor)
    return image
  }
}
struct UsageChoice: Codable { let key: String, label: String }

struct ModelSettings: View {
  @ObservedObject var state: CompanionState
  let host: Host
  func option(_ field: WritableKeyPath<Config, String?>, _ fallback: String = "") -> Binding<String> {
    Binding(get: { state.config[keyPath: field] ?? fallback }, set: { state.config[keyPath: field] = $0 })
  }
  func route(_ title: String, _ field: WritableKeyPath<Config, String?>, whisper: Bool) -> some View {
    Picker(title, selection: option(field, whisper ? "inherit" : "local")) {
      if whisper { Text("跟随聊天").tag("inherit") }
      Text("本地 GGUF").tag("local")
      Text("兼容 API").tag("api")
      Text("Codex 账户").tag("codex")
    }
  }
  @ViewBuilder func selectModel(_ source: String, _ field: WritableKeyPath<Config, String?>, _ title: String) -> some View {
    HStack {
      TextField(title, text: option(field))
      Menu("选择") {
        if source == "codex" { Button("跟随 Codex 默认模型") { state.config[keyPath: field] = "" } }
        ForEach(state.modelLists[source] ?? [], id: \.self) { value in
          Button(value) { state.config[keyPath: field] = value }
        }
        Divider()
        Button("读取可用模型") {
          state.modelFeedback = "正在读取模型列表…"
          host.send(["op":"model-list", "source":source])
        }
      }.fixedSize()
    }
  }
  var body: some View {
    ScrollView {
      Form {
        route("对话来源", \.chatSource, whisper: false)
        route("碎碎念与梦话", \.whisperSource, whisper: true)
        let chat = state.config.chatSource ?? "local"
        let whisper = state.config.whisperSource ?? "inherit"
        if chat == "local" { TextField("聊天 GGUF", text: $state.config.model) }
        if whisper == "local" || (state.config.whisperSource == nil && chat == "local") {
          TextField("碎碎念 GGUF（留空跟随聊天）", text: option(\.whisperModel))
        }
        if chat == "api" || whisper == "api" {
          Divider()
          TextField("API 基址（含 /v1）", text: option(\.apiURL))
          TextField("密钥环境变量名（可选）", text: option(\.apiKeyEnv))
          HStack {
            SecureField("或存入本机钥匙串", text: $state.keyDraft)
            Button("保存密钥", action: saveKey).disabled(state.keyDraft.isEmpty)
          }
          if !state.keyFeedback.isEmpty { Text(state.keyFeedback).font(.caption) }
          Button("测试 API 连接（读取模型列表）") {
            state.modelFeedback = "正在连接所填的 API…"
            host.send(["op":"model-list", "source":"api"])
          }
          if chat == "api" { selectModel("api", \.apiModel, "聊天 API 模型") }
          if whisper == "api" { selectModel("api", \.whisperApiModel, "碎碎念 API 模型") }
        }
        if chat == "codex" || whisper == "codex" {
          Divider()
          if chat == "codex" { selectModel("codex", \.codexModel, "聊天 Codex 模型（留空使用账户默认）") }
          if whisper == "codex" { selectModel("codex", \.whisperCodexModel, "碎碎念 Codex 模型") }
        }
        if !state.modelFeedback.isEmpty { Text(state.modelFeedback).font(.caption) }
        if chat != "local" || ["api","codex"].contains(whisper) {
          Text("所选服务会收到该通道的人设、消息和选用的上下文，使用量按服务账户规则计算。")
            .font(.caption).foregroundStyle(.secondary)
        }
      }.padding(12)
    }
  }
  private func saveKey() {
    guard let url = URLComponents(string: state.config.apiURL ?? ""), let scheme = url.scheme,
      let domain = url.host, ["https","http"].contains(scheme), url.user == nil, url.password == nil,
      scheme == "https" || ["localhost","127.0.0.1","::1"].contains(domain)
    else { state.keyFeedback = "请先填写有效的 API 基址。"; return }
    let name = domain.contains(":") && !domain.hasPrefix("[") ? "[" + domain + "]" : domain
    let origin = scheme + "://" + name + (url.port.map { ":" + String($0) } ?? "")
    let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
      kSecAttrService as String:"local.cartethyia.petplus.api", kSecAttrAccount as String:origin]
    let data: [String: Any] = [kSecValueData as String:Data(state.keyDraft.utf8)]
    var result = SecItemUpdate(query as CFDictionary, data as CFDictionary)
    if result == errSecItemNotFound { result = SecItemAdd(query.merging(data) { _, new in new } as CFDictionary, nil) }
    state.keyFeedback = result == errSecSuccess ? "已存入本机钥匙串" : "保存失败（\(result)）"
    if result == errSecSuccess { state.keyDraft = "" }
  }
}
