import AVFoundation
import Combine
import Foundation

final class AudioPlaybackManager: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var activeSessionID: String?
    @Published var isPlaying = false
    @Published var errorMessage: String?

    private var player: AVAudioPlayer?

    func play(sessionID: String, wavData: Data) {
        stop()
        do {
            let player = try AVAudioPlayer(data: wavData)
            player.delegate = self
            player.prepareToPlay()
            guard player.play() else {
                errorMessage = "Unable to start audio playback."
                return
            }
            self.player = player
            activeSessionID = sessionID
            isPlaying = true
            errorMessage = nil
        } catch {
            errorMessage = "Audio decode failed: \(error.localizedDescription)"
        }
    }

    func stop() {
        player?.stop()
        player = nil
        activeSessionID = nil
        isPlaying = false
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        self.player = nil
        activeSessionID = nil
        isPlaying = false
        if !flag {
            errorMessage = "Playback ended with an error."
        }
    }
}
