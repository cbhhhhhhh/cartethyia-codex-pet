import Foundation
import NaturalLanguage

// One local, bounded string per invocation. Only a boolean leaves the tagger.
let input = FileHandle.standardInput.readDataToEndOfFile()
guard input.count <= 32_768, let sentence = String(data: input, encoding: .utf8) else { exit(2) }
let tagger = NLTagger(tagSchemes: [.nameType])
tagger.string = sentence
var found = false
tagger.enumerateTags(in: sentence.startIndex..<sentence.endIndex, unit: .word, scheme: .nameType,
                     options: [.omitWhitespace, .omitPunctuation, .joinNames]) { tag, _ in
  if tag == .placeName { found = true; return false }
  return true
}
print(found ? "1" : "0")
