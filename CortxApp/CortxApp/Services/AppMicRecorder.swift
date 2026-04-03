import AVFoundation
import Combine
import Foundation

@MainActor
final class AppMicRecorder: NSObject, ObservableObject {
    @Published private(set) var isRecording = false
    @Published var errorMessage: String?

    private var recorder: AVAudioRecorder?
    private var recordingURL: URL?

    let sampleRate: Int = 16_000
    let channels: Int = 1
    let codec: String = "pcm16le"

    func startRecording() async -> Bool {
        errorMessage = nil

        let granted = await requestMicrophonePermission()
        guard granted else {
            errorMessage = "Microphone permission is required."
            return false
        }

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
            try session.setActive(true, options: [])

            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("app_capture_\(Int(Date().timeIntervalSince1970)).wav")
            recordingURL = url

            let settings: [String: Any] = [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: sampleRate,
                AVNumberOfChannelsKey: channels,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false,
                AVLinearPCMIsBigEndianKey: false
            ]

            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.prepareToRecord()
            guard recorder.record() else {
                errorMessage = "Failed to start recording."
                return false
            }

            self.recorder = recorder
            isRecording = true
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func stopRecording() -> URL? {
        guard isRecording else { return nil }
        recorder?.stop()
        recorder = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        return recordingURL
    }

    private func requestMicrophonePermission() async -> Bool {
        if #available(iOS 17.0, *) {
            return await withCheckedContinuation { continuation in
                AVAudioApplication.requestRecordPermission { granted in
                    continuation.resume(returning: granted)
                }
            }
        }

        return await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }
}
