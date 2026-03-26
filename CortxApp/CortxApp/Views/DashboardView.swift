import SwiftUI

struct DashboardView: View {
    @ObservedObject var session: AppSessionViewModel
    @State private var showPairingSheet = false
    @StateObject private var playback = AudioPlaybackManager()
    @State private var loadingAudioSessionID: String?
    @State private var loadingTranscriptSessionID: String?
    @State private var transcriptDisplay: TranscriptDisplay?

    var body: some View {
        ZStack {
            AppBackgroundView()

            ScrollView {
                VStack(spacing: 14) {
                    header

                    if let error = session.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .padding(.horizontal, 16)
                    }

                    if let playbackError = playback.errorMessage {
                        Text(playbackError)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .padding(.horizontal, 16)
                    }

                    devicesCard
                    recordingsCard
                }
                .padding(.bottom, 20)
            }
            .padding(16)
        }
        .sheet(isPresented: $showPairingSheet) {
            PairDeviceSheet(
                session: session,
                onPaired: {
                    Task {
                        await session.refreshPairedDevices()
                        await session.refreshCaptures()
                    }
                }
            )
        }
        .sheet(item: $transcriptDisplay) { data in
            TranscriptView(data: data)
        }
        .task {
            await session.refreshPairedDevices()
            await session.refreshCaptures()
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your Devices")
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                    Text(session.userEmail)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Logout") {
                    session.logout()
                }
                .buttonStyle(.bordered)
            }

            HStack(spacing: 10) {
                Button {
                    showPairingSheet = true
                } label: {
                    Label("Pair Device", systemImage: "dot.radiowaves.left.and.right")
                }
                .buttonStyle(.borderedProminent)

                Button {
                    Task {
                        await session.refreshPairedDevices()
                        await session.refreshCaptures()
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(session.isWorking)
            }
        }
    }

    private var devicesCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Paired")
                .font(.headline)

            if session.pairedDevices.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "bolt.horizontal.circle")
                        .font(.system(size: 34))
                        .foregroundStyle(.blue)
                    Text("No paired device yet")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 22)
            } else {
                ForEach(session.pairedDevices) { device in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text((device.alias?.isEmpty == false ? device.alias : nil) ?? device.device_code)
                                .font(.body.weight(.semibold))
                            Text(device.device_code)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(device.paired_at.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 5)

                    if device.id != session.pairedDevices.last?.id {
                        Divider()
                    }
                }
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.5), lineWidth: 1)
        )
    }

    private var recordingsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Saved Audio")
                    .font(.headline)
                Spacer()
                if playback.isPlaying {
                    Button {
                        playback.stop()
                    } label: {
                        Label("Stop", systemImage: "stop.fill")
                    }
                    .buttonStyle(.bordered)
                }
            }

            if session.captures.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "waveform")
                        .font(.system(size: 30))
                        .foregroundStyle(.blue)
                    Text("No captures yet")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
            } else {
                ForEach(session.captures) { capture in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(capture.device_code)
                                    .font(.body.weight(.semibold))
                                Text(capture.started_at.formatted(date: .abbreviated, time: .shortened))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(capture.status.capitalized)
                                .font(.caption2.weight(.semibold))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(capture.isPlayable ? Color.green.opacity(0.15) : Color.orange.opacity(0.18))
                                .clipShape(Capsule())
                        }

                        HStack(spacing: 10) {
                            Button {
                                Task {
                                    await playCapture(capture)
                                }
                            } label: {
                                if loadingAudioSessionID == capture.id {
                                    ProgressView()
                                } else if playback.activeSessionID == capture.id, playback.isPlaying {
                                    Label("Playing", systemImage: "speaker.wave.2.fill")
                                } else {
                                    Label("Play", systemImage: "play.fill")
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(!capture.isPlayable || loadingAudioSessionID != nil)

                            Button {
                                Task {
                                    await viewTranscript(capture)
                                }
                            } label: {
                                if loadingTranscriptSessionID == capture.id {
                                    ProgressView()
                                } else {
                                    Label("Transcript", systemImage: "text.bubble")
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(loadingTranscriptSessionID != nil)
                        }
                    }
                    .padding(.vertical, 5)

                    if capture.id != session.captures.last?.id {
                        Divider()
                    }
                }
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.5), lineWidth: 1)
        )
    }

    private func playCapture(_ capture: AppCaptureSession) async {
        loadingAudioSessionID = capture.id
        defer { loadingAudioSessionID = nil }

        do {
            let wavData = try await session.fetchAudio(sessionID: capture.id)
            playback.play(sessionID: capture.id, wavData: wavData)
        } catch {
            playback.errorMessage = error.localizedDescription
        }
    }

    private func viewTranscript(_ capture: AppCaptureSession) async {
        loadingTranscriptSessionID = capture.id
        defer { loadingTranscriptSessionID = nil }

        do {
            let transcript = try await session.fetchTranscript(sessionID: capture.id)
            transcriptDisplay = TranscriptDisplay(
                id: capture.id,
                title: capture.device_code,
                body: transcript.full_text
            )
        } catch {
            session.errorMessage = error.localizedDescription
        }
    }
}

private struct TranscriptDisplay: Identifiable {
    let id: String
    let title: String
    let body: String
}

private struct TranscriptView: View {
    @Environment(\.dismiss) private var dismiss
    let data: TranscriptDisplay

    var body: some View {
        NavigationStack {
            ScrollView {
                Text(data.body.isEmpty ? "Transcript is empty." : data.body)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
            .navigationTitle(data.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        dismiss()
                    }
                }
            }
        }
    }
}

struct PairDeviceSheet: View {
    @Environment(\.dismiss) private var dismiss

    @ObservedObject var session: AppSessionViewModel
    @StateObject private var ble = BLEPairingViewModel()
    let onPaired: () -> Void

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                header

                statusCard

                controlsRow

                listContent

                Spacer(minLength: 0)
            }
            .padding(14)
            .navigationTitle("Pair Device")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        ble.stopScanning()
                        dismiss()
                    }
                }
            }
            .onChange(of: ble.pairingStatus) { _, newValue in
                if newValue == .success {
                    onPaired()
                }
            }
            .task {
                // User taps Scan after Bluetooth state settles.
            }
            .onDisappear {
                ble.stopScanning()
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Find your ESP32 device over Bluetooth, then pair with your account.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if let code = ble.discoveredDeviceCode, !code.isEmpty {
                Text("Detected code: \(code)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Circle()
                    .fill(ble.pairingStatus == .success ? Color.green : (ble.isBusy ? Color.orange : Color.blue))
                    .frame(width: 10, height: 10)
                Text(ble.statusMessage)
                    .font(.subheadline.weight(.medium))
            }

            if let error = ble.errorMessage {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(.ultraThinMaterial)
        )
    }

    private var controlsRow: some View {
        HStack(spacing: 10) {
            Button {
                ble.startScanning()
            } label: {
                Label("Scan", systemImage: "magnifyingglass")
            }
            .buttonStyle(.borderedProminent)
            .disabled(!ble.bluetoothReady)

            Button {
                ble.stopScanning()
            } label: {
                Label("Stop", systemImage: "stop.circle")
            }
            .buttonStyle(.bordered)
            .disabled(!ble.isScanning)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var listContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            if ble.devices.isEmpty {
                VStack(spacing: 8) {
                    if ble.isScanning {
                        ProgressView()
                        Text("Scanning for nearby SecondMind devices")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    } else if ble.bluetoothReady {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .font(.system(size: 24))
                            .foregroundStyle(.blue)
                        Text("Tap Scan to find nearby SecondMind devices")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    } else {
                        Image(systemName: "bolt.slash")
                            .font(.system(size: 24))
                            .foregroundStyle(.orange)
                        Text("Turn on Bluetooth and allow access, then tap Scan")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 26)
            } else {
                List(ble.devices) { device in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(device.name)
                                .font(.body.weight(.semibold))
                            Text("RSSI \(device.rssi)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("Pair") {
                            guard let appToken = session.pairingAccessToken() else {
                                session.errorMessage = "You must be logged in to pair."
                                return
                            }
                            ble.pair(with: device, appToken: appToken, apiClient: session.api())
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(ble.isBusy)
                    }
                    .padding(.vertical, 4)
                }
                .listStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
