// PDF2DOCX AI Fidelity local OCR bridge. Apple frameworks are provided by macOS.
import Foundation
import Vision
import ImageIO

struct Observation: Codable {
    let text: String
    let confidence: Float
    let x0: Double
    let y0: Double
    let x1: Double
    let y1: Double
    let line: String
}

do {
    guard CommandLine.arguments.count >= 3 else {
        throw NSError(domain: "pdf2docx", code: 1, userInfo: [NSLocalizedDescriptionKey: "Usage: vision IMAGE LANGUAGE"])
    }
    let language = CommandLine.arguments[2]
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = language == "it+en" ? ["it-IT", "en-US"] : [language == "it" ? "it-IT" : "en-US"]
    request.minimumTextHeight = 0.001
    if CommandLine.arguments[1] == "--health" {
        let languages = try request.supportedRecognitionLanguages()
        let data = try JSONSerialization.data(withJSONObject: ["available": true, "languages": languages])
        print(String(decoding: data, as: UTF8.self))
        exit(0)
    }
    let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
    guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "pdf2docx", code: 2, userInfo: [NSLocalizedDescriptionKey: "Cannot open input crop"])
    }
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])
    let w = Double(cgImage.width)
    let h = Double(cgImage.height)
    let observations = (request.results ?? []).enumerated().compactMap { index, item -> Observation? in
        guard let candidate = item.topCandidates(1).first else { return nil }
        let b = item.boundingBox
        return Observation(text: candidate.string, confidence: candidate.confidence,
                           x0: b.minX * w, y0: (1 - b.maxY) * h,
                           x1: b.maxX * w, y1: (1 - b.minY) * h, line: String(index))
    }
    let encoder = JSONEncoder()
    print(String(decoding: try encoder.encode(observations), as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}

