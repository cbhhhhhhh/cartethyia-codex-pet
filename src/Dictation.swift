import AVFoundation
import AppKit
import Speech

final class LocalDictation {
  private let engine = AVAudioEngine()
  private var request: SFSpeechAudioBufferRecognitionRequest?, task: SFSpeechRecognitionTask?
  private var pressed = false, installed = false, generation = 0
  private weak var host: Host?
  private var startTime = 0.0, heardWords = false
  private var prefix = ""
  func start(_ host: Host) {
    guard !pressed else { return }
    cancel()
    pressed = true
    generation += 1
    let g = generation
    self.host = host
    prefix = host.s.draft
    heardWords = false
    startTime = 0
    guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN")),
      recognizer.supportsOnDeviceRecognition
    else {
      host.card.note = "此 Mac 暂无可用的本地中文听写。"
      return
    }
    SFSpeechRecognizer.requestAuthorization { [weak self] status in
      DispatchQueue.main.async {
        guard let self = self, self.pressed, self.generation == g else { return }
        guard status == .authorized else {
          host.card.note = "请在系统隐私设置中允许语音识别。"
          return
        }
        AVCaptureDevice.requestAccess(for: .audio) { [weak self] allowed in
          DispatchQueue.main.async {
            guard let self = self, self.pressed, self.generation == g else { return }
            guard allowed else {
              host.card.note = "请在系统隐私设置中允许麦克风。"
              return
            }
            let req = SFSpeechAudioBufferRecognitionRequest()
            req.requiresOnDeviceRecognition = true
            req.shouldReportPartialResults = true
            self.request = req
            let node = self.engine.inputNode
            let format = node.outputFormat(forBus: 0)
            guard format.channelCount > 0, format.sampleRate > 0 else {
              host.card.note = "未找到可用麦克风。"
              return
            }
            node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
              req.append(buffer)
            }
            self.installed = true
            self.task = recognizer.recognitionTask(with: req) { [weak self] result, error in
              DispatchQueue.main.async {
                guard let self = self, self.generation == g else { return }
                if let result = result {
                  self.heardWords = !result.bestTranscription.formattedString.isEmpty
                  host.s.draft = self.prefix + result.bestTranscription.formattedString
                }
                if error != nil || result?.isFinal == true {
                  let empty = !self.heardWords
                  self.cancel()
                  if empty {
                    host.card.note = "没有听清，请再试一次。"
                    host.surface(.compose)
                  }
                }
              }
            }
            do {
              try self.engine.start()
              host.card.note = "松开结束听写"
              self.startTime = ProcessInfo.processInfo.systemUptime
              host.card.recording = true
            } catch {
              self.cancel()
              host.card.note = "无法启动麦克风。"
            }
          }
        }
      }
    }
  }
  func release() {
    let short = startTime > 0 && ProcessInfo.processInfo.systemUptime - startTime < 0.25
    if short {
      cancel()
      host?.s.draft = prefix
      host?.card.note = "按住话筒再说话。"
    } else {
      stop()
    }
  }
  func stop() {
    pressed = false
    if installed {
      engine.stop()
      engine.inputNode.removeTap(onBus: 0)
      installed = false
    }
    request?.endAudio()
    host?.card.recording = false
    if host?.card.note == "松开结束听写" { host?.card.note = "" }
  }
  func cancel() {
    generation += 1
    stop()
    task?.cancel()
    task = nil
    request = nil
  }
}
