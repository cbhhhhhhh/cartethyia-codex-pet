import AVFoundation
import Foundation

let voice = AVSpeechSynthesisVoice(language: "zh-CN")
let speech = AVSpeechSynthesizer()
let line = AVSpeechUtterance(string: "任务完成。")
line.voice = voice
line.volume = 0.45
var frames = 0
var finished = false
speech.write(line) { buffer in
    guard let pcm = buffer as? AVAudioPCMBuffer else { return }
    let length = Int(pcm.frameLength)
    DispatchQueue.main.async {
        frames += length
        if length == 0 { finished = true }
    }
}
let deadline = Date().addingTimeInterval(15)
while !finished && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.05)) }
let result: [String:Any] = ["frames":frames,"voice":voice?.language ?? "unavailable","audio_played":false]
FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted]))
exit(frames > 0 ? 0 : 1)
