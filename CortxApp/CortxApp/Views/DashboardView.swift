import SwiftUI

struct DashboardView: View {
    @ObservedObject var session: AppSessionViewModel
    @State private var showPairingSheet = false
    @StateObject private var bleGateway = BLEPairingViewModel()
    @StateObject private var playback = AudioPlaybackManager()
    @State private var loadingAudioSessionID: String?
    @State private var reveal = false
    @State private var showDeleteAccountSheet = false

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

                    if let liveError = bleGateway.liveErrorMessage {
                        Text(liveError)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .padding(.horizontal, 16)
                    }

                    devicesCard
                    liveGatewayCard
                    recordingsCard
                }
                .opacity(reveal ? 1 : 0)
                .offset(y: reveal ? 0 : 16)
                .animation(.easeOut(duration: 0.45), value: reveal)
                .padding(.bottom, 20)
            }
            .padding(16)
        }
        .sheet(isPresented: $showPairingSheet) {
            PairDeviceSheet(
                session: session,
                ble: bleGateway,
                onPaired: {
                    Task {
                        await session.refreshPairedDevices()
                        await session.refreshCaptures()
                    }
                }
            )
        }
        .sheet(isPresented: $showDeleteAccountSheet) {
            DeleteAccountSheet(session: session)
        }
        .task {
            await session.refreshPairedDevices()
            await session.refreshCaptures()
        }
        .onAppear {
            reveal = true
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your Devices")
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                    Text(session.userDisplayName)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    if session.shouldShowEmailAsSubtitle {
                        Text(session.userEmail)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 8) {
                    Button("Logout") {
                        session.logout()
                    }
                    .buttonStyle(LiquidSecondaryButtonStyle())

                    Button("Delete Account") {
                        showDeleteAccountSheet = true
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.red)
                }
            }

            HStack(spacing: 10) {
                Button {
                    showPairingSheet = true
                } label: {
                    Label("Pair Device", systemImage: "dot.radiowaves.left.and.right")
                }
                .buttonStyle(LiquidPrimaryButtonStyle())

                Button {
                    Task {
                        await session.refreshPairedDevices()
                        await session.refreshCaptures()
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(LiquidSecondaryButtonStyle())
                .disabled(session.isWorking)
            }
        }
        .padding(14)
        .liquidCard()
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
        .liquidCard()
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
                    .buttonStyle(LiquidSecondaryButtonStyle())
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
                            .buttonStyle(LiquidPrimaryButtonStyle())
                            .disabled(!capture.isPlayable || loadingAudioSessionID != nil)
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
        .liquidCard()
    }

    private var liveGatewayCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Live Gateway")
                .font(.headline)

            Text(bleGateway.liveStatusMessage)
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Circle()
                    .fill(livePhaseColor)
                    .frame(width: 8, height: 8)
                Text(livePhaseText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            if bleGateway.isLiveStreaming {
                HStack(spacing: 12) {
                    Text("Frames: \(bleGateway.liveFramesSent)")
                        .font(.caption2)
                    Text("Packets: \(bleGateway.livePacketsReceived)")
                        .font(.caption2)
                    Text("Drops: \(bleGateway.livePacketDrops)")
                        .font(.caption2)
                }
                .foregroundStyle(.secondary)
            }

            if !bleGateway.liveTransportLogs.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(bleGateway.liveTransportLogs.suffix(40).enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .font(.system(size: 11, weight: .regular, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .frame(minHeight: 120, maxHeight: 180)
                .padding(10)
                .background(Color.black.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }

            HStack(spacing: 10) {
                Button {
                    startLiveGateway()
                } label: {
                    if bleGateway.livePhase.isBusy && bleGateway.livePhase != .stopping {
                        HStack(spacing: 8) {
                            ProgressView()
                                .controlSize(.small)
                                .tint(.white)
                            Text(liveStartButtonTitle)
                        }
                    } else {
                        Label(liveStartButtonTitle, systemImage: liveStartButtonSymbol)
                    }
                }
                .buttonStyle(LiquidPrimaryButtonStyle())
                .disabled(bleGateway.isLiveStreaming || session.pairedDevices.isEmpty)

                Button {
                    bleGateway.stopLiveStreaming()
                    Task {
                        try? await Task.sleep(nanoseconds: 1_000_000_000)
                        await session.refreshCaptures()
                    }
                } label: {
                    if bleGateway.livePhase == .stopping {
                        HStack(spacing: 8) {
                            ProgressView()
                                .controlSize(.small)
                            Text("Stopping...")
                        }
                    } else {
                        Label("Stop Live", systemImage: "stop.fill")
                    }
                }
                .buttonStyle(LiquidSecondaryButtonStyle())
                .disabled(!bleGateway.isLiveStreaming)
            }
        }
        .padding(14)
        .liquidCard()
    }

    private func startLiveGateway() {
        guard let token = session.pairingAccessToken() else {
            session.errorMessage = "Login expired. Please log in again."
            return
        }
        guard let deviceCode = session.pairedDevices.first?.device_code else {
            session.errorMessage = "No paired device available."
            return
        }
        bleGateway.startLiveStreaming(
            deviceCode: deviceCode,
            appToken: token,
            apiClient: session.api()
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

    private var liveStartButtonTitle: String {
        switch bleGateway.livePhase {
        case .idle, .failed:
            return "Start Live"
        case .starting:
            return "Starting..."
        case .connectingBLE:
            return "Connecting BLE..."
        case .waitingAudio:
            return "Waiting Audio..."
        case .streaming:
            return "Live Running"
        case .stopping:
            return "Stopping..."
        }
    }

    private var liveStartButtonSymbol: String {
        switch bleGateway.livePhase {
        case .streaming:
            return "waveform.badge.mic"
        case .failed:
            return "exclamationmark.triangle.fill"
        default:
            return "dot.radiowaves.left.and.right"
        }
    }

    private var livePhaseText: String {
        switch bleGateway.livePhase {
        case .idle:
            return "Idle"
        case .starting:
            return "Starting"
        case .connectingBLE:
            return "Connecting BLE"
        case .waitingAudio:
            return "Waiting for device audio"
        case .streaming:
            return "Streaming"
        case .stopping:
            return "Stopping"
        case .failed:
            return "Failed"
        }
    }

    private var livePhaseColor: Color {
        switch bleGateway.livePhase {
        case .idle:
            return .gray
        case .starting, .connectingBLE, .waitingAudio, .stopping:
            return .orange
        case .streaming:
            return .green
        case .failed:
            return .red
        }
    }
}

private struct DeleteAccountSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var session: AppSessionViewModel

    @State private var password = ""
    @State private var confirmText = ""
    @State private var localMessage: String?

    private let confirmationWord = "DELETE"

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text("This permanently deletes your account and unbinds your paired devices.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Text("Type \(confirmationWord) to confirm")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                TextField("Type DELETE", text: $confirmText)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .textFieldStyle(.roundedBorder)

                SecureField("Current password", text: $password)
                    .textContentType(.password)
                    .textFieldStyle(.roundedBorder)

                Button {
                    Task {
                        await deleteAccount()
                    }
                } label: {
                    if session.isWorking {
                        ProgressView()
                            .tint(.white)
                    } else {
                        Label("Delete My Account", systemImage: "trash")
                    }
                }
                .buttonStyle(LiquidPrimaryButtonStyle())
                .disabled(confirmText.uppercased() != confirmationWord || password.count < 8 || session.isWorking)

                if let localMessage {
                    Text(localMessage)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if let error = session.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }

                Spacer()
            }
            .padding(16)
            .navigationTitle("Delete Account")
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

    private func deleteAccount() async {
        guard confirmText.uppercased() == confirmationWord else {
            localMessage = "Type \(confirmationWord) to confirm."
            return
        }

        let success = await session.deleteAccount(password: password)
        guard success else { return }

        localMessage = "Account deleted."
        dismiss()
    }
}

struct PairDeviceSheet: View {
    @Environment(\.dismiss) private var dismiss

    @ObservedObject var session: AppSessionViewModel
    @ObservedObject var ble: BLEPairingViewModel
    @State private var wifiSSID = ""
    @State private var wifiPassword = ""
    @State private var queueingWifi = false
    let onPaired: () -> Void

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                header

                statusCard

                controlsRow
                wifiCard

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
                ble.disconnect()
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
        .liquidCard()
    }

    private var controlsRow: some View {
            HStack(spacing: 10) {
                Button {
                    ble.startScanning()
                } label: {
                    Label("Scan", systemImage: "magnifyingglass")
                }
            .buttonStyle(LiquidPrimaryButtonStyle())
            .disabled(!ble.bluetoothReady)

            Button {
                ble.stopScanning()
            } label: {
                Label("Stop", systemImage: "stop.circle")
            }
            .buttonStyle(LiquidSecondaryButtonStyle())
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
                        .buttonStyle(LiquidPrimaryButtonStyle())
                        .disabled(ble.isBusy)
                    }
                    .padding(.vertical, 4)
                }
                .listStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var wifiCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Device Wi-Fi Setup")
                .font(.subheadline.weight(.semibold))
            Text("Use your home Wi-Fi or phone hotspot SSID/password. Send over BLE for immediate setup, or queue in backend for next online pull.")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextField("Wi-Fi SSID", text: $wifiSSID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)
            SecureField("Wi-Fi password", text: $wifiPassword)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)

            HStack(spacing: 10) {
                Button {
                    ble.sendWifiConfig(ssid: wifiSSID, password: wifiPassword)
                } label: {
                    if ble.isSendingWifiConfig {
                        ProgressView()
                    } else {
                        Label("Send over BLE", systemImage: "antenna.radiowaves.left.and.right")
                    }
                }
                .buttonStyle(LiquidPrimaryButtonStyle())
                .disabled(!ble.canConfigureWifi || ble.isSendingWifiConfig || wifiSSID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                Button {
                    Task {
                        await queueWifiInBackend()
                    }
                } label: {
                    if queueingWifi {
                        ProgressView()
                    } else {
                        Label("Queue in backend", systemImage: "tray.and.arrow.down")
                    }
                }
                .buttonStyle(LiquidSecondaryButtonStyle())
                .disabled(queueingWifi || wifiSSID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            Text("Device Wi-Fi status: \(ble.wifiStatusMessage)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .liquidCard()
    }

    private func queueWifiInBackend() async {
        let normalizedSSID = wifiSSID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedSSID.isEmpty else {
            session.errorMessage = "SSID is required."
            return
        }
        guard let appToken = session.pairingAccessToken() else {
            session.errorMessage = "You must be logged in."
            return
        }
        guard
            let deviceCode = ble.discoveredDeviceCode?.trimmingCharacters(in: .whitespacesAndNewlines),
            !deviceCode.isEmpty,
            let paired = session.pairedDevices.first(where: { $0.device_code.caseInsensitiveCompare(deviceCode) == .orderedSame })
        else {
            session.errorMessage = "Pair the device first so backend can map network profile to it."
            return
        }

        queueingWifi = true
        defer { queueingWifi = false }

        do {
            let response = try await session.api().queueDeviceNetworkProfile(
                deviceID: paired.device_id,
                ssid: normalizedSSID,
                password: wifiPassword,
                source: "app_manual",
                accessToken: appToken
            )
            ble.wifiStatusMessage = "Queued in backend (\(response.expires_in_seconds / 60) min TTL)."
        } catch {
            session.errorMessage = error.localizedDescription
        }
    }
}
