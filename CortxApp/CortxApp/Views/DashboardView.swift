import SwiftUI

struct DashboardView: View {
    @ObservedObject var session: AppSessionViewModel
    @State private var showPairingSheet = false
    @State private var showProfileSheet = false
    @StateObject private var bleGateway = BLEPairingViewModel()
    @StateObject private var micRecorder = AppMicRecorder()
    @StateObject private var playback = AudioPlaybackManager()
    @State private var loadingAudioSessionID: String?
    @State private var loadingTranscriptSessionIDs: Set<String> = []
    @State private var loadingAISessionIDs: Set<String> = []
    @State private var transcriptsBySessionID: [String: AppCaptureTranscript] = [:]
    @State private var transcriptErrorsBySessionID: [String: String] = [:]
    @State private var aiBySessionID: [String: AppCaptureAIResponse] = [:]
    @State private var aiErrorsBySessionID: [String: String] = [:]
    @State private var assistantMessage: String?
    @State private var reveal = false
    @State private var showDeleteAccountSheet = false
    @State private var selectedMemory: AppCaptureSession?
    @State private var selectedSummaryDeviceID: String?
    @State private var renameDeviceTarget: PairedDevice?
    @State private var renameAliasText = ""
    @State private var networkProfileTarget: PairedDevice?
    @State private var networkSSIDText = ""
    @State private var networkPasswordText = ""
    @State private var unpairTarget: PairedDevice?
    private let calendarService = CalendarService()
    @State private var showIdeaGraph = false

    var body: some View {
        ZStack {
            AppBackgroundView()

            if showIdeaGraph {
                IdeaGraphView(
                    session: session,
                    onClose: {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.85)) {
                            showIdeaGraph = false
                        }
                    }
                )
                .transition(.move(edge: .trailing).combined(with: .opacity))
            } else {

            ScrollView {
                VStack(spacing: 14) {
                    header
                    dailySummaryCard

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

                    if let bleError = bleGateway.errorMessage {
                        Text(bleError)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .padding(.horizontal, 16)
                    }

                    if let micError = micRecorder.errorMessage {
                        Text(micError)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .padding(.horizontal, 16)
                    }

                    if let assistantMessage {
                        Text(assistantMessage)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 16)
                    }

                    devicesCard
                    memoryBoardCard
                }
                .opacity(reveal ? 1 : 0)
                .offset(y: reveal ? 0 : 16)
                .animation(.easeOut(duration: 0.45), value: reveal)
                .padding(.bottom, 20)
            }
            .padding(16)
        } // end else (dashboard mode)
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
        .sheet(isPresented: $showProfileSheet) {
            ProfileSheet(session: session)
        }
        .sheet(item: $renameDeviceTarget) { device in
            renameDeviceSheet(device)
        }
        .sheet(item: $networkProfileTarget) { device in
            networkProfileSheet(device)
        }
        .sheet(item: $selectedMemory) { capture in
            MemoryDetailSheet(
                capture: capture,
                transcript: transcriptsBySessionID[capture.id],
                transcriptError: transcriptErrorsBySessionID[capture.id],
                extraction: aiBySessionID[capture.id]?.extraction,
                items: memoryItems(for: capture),
                aiError: aiErrorsBySessionID[capture.id],
                isTranscriptLoading: loadingTranscriptSessionIDs.contains(capture.id),
                isAILoading: loadingAISessionIDs.contains(capture.id),
                isPlaying: playback.activeSessionID == capture.id && playback.isPlaying,
                onPlay: {
                    Task { await playCapture(capture) }
                },
                onLoadTranscript: {
                    Task { await loadTranscript(capture, silentNotReady: false) }
                },
                onLoadAI: {
                    Task { await loadCaptureAI(capture) }
                },
                onReprocess: {
                    Task { await reprocessCaptureAI(capture) }
                },
                onRefreshAll: {
                    Task {
                        await session.refreshCaptures(showLoader: false)
                        await session.refreshAssistantItems(showLoader: false)
                        await loadTranscript(capture, silentNotReady: true)
                        await loadCaptureAI(capture)
                    }
                },
                onSetItemStatus: { item, newStatus in
                    Task { await setAssistantItemStatus(item, status: newStatus) }
                },
                onSnooze: { item, minutes in
                    Task { await snoozeReminder(item, minutes: minutes) }
                },
                onAddToCalendar: { item in
                    Task { await addReminderToCalendar(item) }
                }
            )
        }
        .alert("Unpair Device?", isPresented: Binding(
            get: { unpairTarget != nil },
            set: { isPresented in
                if !isPresented {
                    unpairTarget = nil
                }
            }
        )) {
            Button("Cancel", role: .cancel) {
                unpairTarget = nil
            }
            Button("Unpair", role: .destructive) {
                guard let device = unpairTarget else { return }
                Task {
                    let ok = await session.unpairDevice(deviceID: device.id)
                    if ok {
                        assistantMessage = "Device \(device.device_code) unpaired."
                    }
                    unpairTarget = nil
                }
            }
        } message: {
            Text("This removes the device from your account until you pair again.")
        }
        .task {
            await session.refreshCurrentUser(showLoader: false)
            await session.refreshUserPreferences(showLoader: false)
            await session.refreshPairedDevices(showLoader: false)
            await session.refreshCaptures(showLoader: false)
            await session.refreshAssistantItems(showLoader: false)
            await session.refreshDailySummary(showLoader: false)
        }
        .task {
            await pollDashboardData()
        }
        .onAppear {
            reveal = true
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your Workspace")
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
                    Button("Profile") {
                        showProfileSheet = true
                    }
                    .buttonStyle(LiquidSecondaryButtonStyle())

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

            LazyVGrid(
                columns: [
                    GridItem(.flexible(), spacing: 10),
                    GridItem(.flexible(), spacing: 10)
                ],
                spacing: 10
            ) {
                Button {
                    Task { await handleMicButtonTap() }
                } label: {
                    Label(
                        micRecorder.isRecording ? "Stop Mic" : "Record Mic",
                        systemImage: micRecorder.isRecording ? "stop.circle.fill" : "mic.fill"
                    )
                    .lineLimit(1)
                    .minimumScaleFactor(0.9)
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(LiquidPrimaryButtonStyle())
                .disabled(session.isWorking)

                Button {
                    showPairingSheet = true
                } label: {
                    Label("Pair Device", systemImage: "dot.radiowaves.left.and.right")
                        .lineLimit(1)
                        .minimumScaleFactor(0.9)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(LiquidPrimaryButtonStyle())

                Button {
                    Task {
                        await session.refreshCurrentUser()
                        await session.refreshUserPreferences()
                        await session.refreshPairedDevices()
                        await session.refreshCaptures()
                        await session.refreshDailySummary()
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                        .lineLimit(1)
                        .minimumScaleFactor(0.9)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(LiquidSecondaryButtonStyle())
                .disabled(session.isWorking)

                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        showIdeaGraph = true
                    }
                } label: {
                    Label("Idea Graph", systemImage: "circle.grid.cross.fill")
                        .lineLimit(1)
                        .minimumScaleFactor(0.9)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(LiquidPrimaryButtonStyle())
            }
        }
        .padding(14)
        .liquidCard()
    }

    private var dailySummaryCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Today Snapshot")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                    Text("Daily summary across your memories")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task {
                        await session.refreshDailySummary(
                            showLoader: false,
                            deviceID: selectedSummaryDeviceID
                        )
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(LiquidSecondaryButtonStyle())
            }

            if !session.pairedDevices.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        summaryDeviceChip(label: "All Devices", isSelected: selectedSummaryDeviceID == nil) {
                            selectedSummaryDeviceID = nil
                            Task { await session.refreshDailySummary(showLoader: false, deviceID: nil) }
                        }
                        ForEach(session.pairedDevices) { device in
                            summaryDeviceChip(
                                label: (device.alias?.isEmpty == false ? device.alias : nil) ?? device.device_code,
                                isSelected: selectedSummaryDeviceID == device.id
                            ) {
                                selectedSummaryDeviceID = device.id
                                Task { await session.refreshDailySummary(showLoader: false, deviceID: device.id) }
                            }
                        }
                    }
                }
            }

            if let summary = session.dailySummary {
                Text(summary.headline)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineSpacing(2)

                HStack(spacing: 8) {
                    summaryMetricChip("\(summary.metrics.memories_count) memories", icon: "waveform")
                    summaryMetricChip("\(summary.metrics.open_actions_due_count) due", icon: "checkmark.circle")
                    summaryMetricChip("\(summary.metrics.upcoming_events_count) upcoming", icon: "calendar")
                }

                if !summary.focus_items.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Focus")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        ForEach(summary.focus_items) { item in
                            HStack {
                                Image(systemName: item.item_type == "reminder" ? "bell.badge" : "list.bullet")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(item.title)
                                    .font(.footnote)
                                Spacer()
                                if let dueAt = item.due_at {
                                    Text(dueAt.formatted(date: .omitted, time: .shortened))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            } else {
                Text("Summary loading...")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
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
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text((device.alias?.isEmpty == false ? device.alias : nil) ?? device.device_code)
                                    .font(.body.weight(.semibold))
                                Text(device.device_code)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            deviceStatusBadge(device.status)
                        }

                        HStack(spacing: 10) {
                            if let lastSeen = device.last_seen_at {
                                Text("Last seen: \(lastSeen.formatted(date: .omitted, time: .shortened))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            } else {
                                Text("Last seen: never")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            if let firmware = device.firmware_version, !firmware.isEmpty {
                                Text("FW: \(firmware)")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            if let lastCapture = device.last_capture_at {
                                Text("Capture: \(lastCapture.formatted(date: .abbreviated, time: .shortened))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        HStack(spacing: 8) {
                            Button("Rename") {
                                renameAliasText = device.alias ?? ""
                                renameDeviceTarget = device
                            }
                            .buttonStyle(LiquidSecondaryButtonStyle())

                            Button("Network") {
                                networkSSIDText = ""
                                networkPasswordText = ""
                                networkProfileTarget = device
                            }
                            .buttonStyle(LiquidSecondaryButtonStyle())

                            Button("Unpair") {
                                unpairTarget = device
                            }
                            .buttonStyle(LiquidSecondaryButtonStyle())
                        }
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

    private var memoryBoardCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Memory Dashboard")
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                    Text("Every conversation becomes a memory card.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task {
                        await session.refreshCaptures()
                        await session.refreshAssistantItems(showLoader: false)
                        await session.refreshDailySummary(showLoader: false, deviceID: selectedSummaryDeviceID)
                        await prefetchReadyTranscripts()
                        await prefetchCaptureAI()
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(LiquidSecondaryButtonStyle())
                .disabled(session.isWorking)
            }

            if session.captures.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "sparkles.tv")
                        .font(.system(size: 34))
                        .foregroundStyle(.blue)
                    Text("No memories yet")
                        .font(.headline)
                    Text("Record from your device and each conversation will appear here.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
            } else {
                ForEach(session.captures) { capture in
                    memoryRow(capture)
                }
            }
        }
        .padding(14)
        .liquidCard()
    }

    @ViewBuilder
    private func memoryRow(_ capture: AppCaptureSession) -> some View {
        let extraction = aiBySessionID[capture.id]?.extraction
        let items = memoryItems(for: capture)
        let reminderCount = items.filter { $0.item_type == "reminder" }.count
        let actionCount = items.filter { $0.item_type == "task" || $0.item_type == "plan_step" }.count
        let intentLabel = extraction?.intent?.isEmpty == false ? extraction?.intent ?? "unknown" : "pending"
        let summary = extraction?.summary?.isEmpty == false
        ? extraction?.summary ?? ""
        : transcriptPreview(for: capture)

        Button {
            openMemory(capture)
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(capture.device_code)
                            .font(.headline.weight(.bold))
                        Text(capture.started_at.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(capture.playbackAvailabilityLabel)
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(capture.has_audio ? Color.green.opacity(0.15) : Color.orange.opacity(0.18))
                        .clipShape(Capsule())
                }

                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)

                HStack(alignment: .center) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            memoryBadge("Intent: \(intentLabel)", icon: "scope")
                            memoryBadge("\(actionCount) actions", icon: "checklist")
                            memoryBadge("\(reminderCount) reminders", icon: "calendar.badge.clock")
                        }
                    }
                    .scrollBounceBehavior(.basedOnSize, axes: .horizontal)

                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.10),
                                Color(red: 0.74, green: 0.89, blue: 0.95).opacity(0.12)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(0.25), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func memoryBadge(_ text: String, icon: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
            Text(text)
        }
        .font(.caption2.weight(.semibold))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.white.opacity(0.12))
        .clipShape(Capsule())
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

    private func memoryItems(for capture: AppCaptureSession) -> [AppAssistantItem] {
        if let aiItems = aiBySessionID[capture.id]?.items, !aiItems.isEmpty {
            return aiItems
        }
        return session.assistantItems.filter { $0.session_id == capture.id }
    }

    private func transcriptPreview(for capture: AppCaptureSession) -> String {
        if let transcript = transcriptsBySessionID[capture.id], !transcript.full_text.isEmpty {
            return transcript.full_text
        }
        if let error = transcriptErrorsBySessionID[capture.id], !error.isEmpty {
            return error
        }
        return "Open memory to load AI summary, intent, reminders, and calendar events."
    }

    private func openMemory(_ capture: AppCaptureSession) {
        selectedMemory = capture
        Task {
            await loadTranscript(capture, silentNotReady: true)
            await loadCaptureAI(capture)
        }
    }

    private func loadCaptureAI(_ capture: AppCaptureSession) async {
        if loadingAISessionIDs.contains(capture.id) {
            return
        }
        loadingAISessionIDs.insert(capture.id)
        defer { loadingAISessionIDs.remove(capture.id) }

        do {
            let response = try await session.fetchCaptureAI(sessionID: capture.id)
            aiBySessionID[capture.id] = response
            aiErrorsBySessionID.removeValue(forKey: capture.id)
        } catch {
            aiErrorsBySessionID[capture.id] = error.localizedDescription
        }
    }

    private func reprocessCaptureAI(_ capture: AppCaptureSession) async {
        do {
            _ = try await session.reprocessCaptureAI(sessionID: capture.id)
            assistantMessage = "AI reprocess queued for \(capture.device_code)."
            await loadCaptureAI(capture)
            await session.refreshAssistantItems(showLoader: false)
        } catch {
            assistantMessage = error.localizedDescription
        }
    }

    private func prefetchCaptureAI() async {
        let doneCaptures = session.captures.filter { $0.status.lowercased() == "done" }
        for capture in doneCaptures.prefix(4) {
            if aiBySessionID[capture.id] == nil && !loadingAISessionIDs.contains(capture.id) {
                await loadCaptureAI(capture)
            }
        }
    }

    private func pollDashboardData() async {
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            guard session.isAuthenticated else { continue }
            await session.refreshCaptures(showLoader: false)
            await session.refreshPairedDevices(showLoader: false)
            await session.refreshAssistantItems(showLoader: false)
            await session.refreshDailySummary(showLoader: false, deviceID: selectedSummaryDeviceID)
            await prefetchReadyTranscripts()
            await prefetchCaptureAI()
        }
    }

    private func prefetchReadyTranscripts() async {
        let ready = session.captures.filter {
            $0.status.lowercased() == "done" &&
            transcriptsBySessionID[$0.id] == nil &&
            !loadingTranscriptSessionIDs.contains($0.id)
        }

        for capture in ready.prefix(8) {
            await loadTranscript(capture, silentNotReady: true)
        }
    }

    private func loadTranscript(_ capture: AppCaptureSession, silentNotReady: Bool) async {
        if loadingTranscriptSessionIDs.contains(capture.id) {
            return
        }

        loadingTranscriptSessionIDs.insert(capture.id)
        defer { loadingTranscriptSessionIDs.remove(capture.id) }

        do {
            let transcript = try await session.fetchTranscript(sessionID: capture.id)
            transcriptsBySessionID[capture.id] = transcript
            transcriptErrorsBySessionID.removeValue(forKey: capture.id)
        } catch let apiError as APIClientError {
            switch apiError {
            case .server(let message):
                let lower = message.lowercased()
                if lower.contains("not ready") || lower.contains("transcribing") {
                    if !silentNotReady {
                        transcriptErrorsBySessionID[capture.id] = "Transcript is not ready yet. Try again in a few seconds."
                    }
                } else {
                    transcriptErrorsBySessionID[capture.id] = message
                }
            default:
                transcriptErrorsBySessionID[capture.id] = apiError.localizedDescription
            }
        } catch {
            transcriptErrorsBySessionID[capture.id] = error.localizedDescription
        }
    }

    private func setAssistantItemStatus(_ item: AppAssistantItem, status: String) async {
        do {
            _ = try await session.updateAssistantItem(itemID: item.id, status: status)
            await session.refreshAssistantItems(showLoader: false)
        } catch {
            assistantMessage = error.localizedDescription
        }
    }

    private func snoozeReminder(_ item: AppAssistantItem, minutes: Int) async {
        do {
            _ = try await session.updateAssistantItem(
                itemID: item.id,
                timezone: TimeZone.current.identifier,
                snoozeMinutes: minutes
            )
            await session.refreshAssistantItems(showLoader: false)
        } catch {
            assistantMessage = error.localizedDescription
        }
    }

    private func addReminderToCalendar(_ item: AppAssistantItem) async {
        guard let dueAt = item.due_at else {
            assistantMessage = "Reminder does not have a due time."
            return
        }

        do {
            try await calendarService.addReminderToCalendar(
                title: item.title,
                details: item.details,
                dueAt: dueAt
            )
            assistantMessage = "Added reminder to Calendar."
        } catch {
            assistantMessage = error.localizedDescription
        }
    }

    private func handleMicButtonTap() async {
        if micRecorder.isRecording {
            guard let fileURL = micRecorder.stopRecording() else {
                assistantMessage = "No recording found to upload."
                return
            }

            do {
                let wavData = try Data(contentsOf: fileURL)
                if wavData.isEmpty {
                    assistantMessage = "Recorded audio is empty."
                    return
                }

                let response = await session.uploadAppCaptureWAV(
                    wavData: wavData,
                    sampleRate: micRecorder.sampleRate,
                    channels: micRecorder.channels,
                    codec: micRecorder.codec
                )

                if let response {
                    assistantMessage = "Uploaded memory: \(response.session_id)"
                    await session.refreshCaptures(showLoader: false)
                    await session.refreshAssistantItems(showLoader: false)
                    await session.refreshDailySummary(showLoader: false, deviceID: selectedSummaryDeviceID)
                } else {
                    assistantMessage = session.errorMessage ?? "Failed to upload recording."
                }
            } catch {
                assistantMessage = error.localizedDescription
            }

            try? FileManager.default.removeItem(at: fileURL)
            return
        }

        let started = await micRecorder.startRecording()
        if started {
            assistantMessage = "Recording from iPhone mic... tap Stop Mic to upload."
        } else {
            assistantMessage = micRecorder.errorMessage ?? "Failed to start recording."
        }
    }

    @ViewBuilder
    private func deviceStatusBadge(_ status: String) -> some View {
        let normalized = status.lowercased()
        let color: Color = normalized == "online"
        ? .green
        : (normalized == "recently_active" ? .orange : .gray)
        Text(normalized.replacingOccurrences(of: "_", with: " ").capitalized)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(color.opacity(0.18))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    @ViewBuilder
    private func summaryDeviceChip(label: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(isSelected ? Color.white : Color.primary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(
                            isSelected
                            ? AnyShapeStyle(
                                LinearGradient(
                                    colors: [
                                        Color(red: 0.10, green: 0.53, blue: 0.95),
                                        Color(red: 0.03, green: 0.70, blue: 0.78)
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            : AnyShapeStyle(Color.white.opacity(0.18))
                        )
                )
        }
        .buttonStyle(.plain)
    }

    private func summaryMetricChip(_ text: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
            Text(text)
        }
        .font(.caption2.weight(.semibold))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(Color.white.opacity(0.14))
        .clipShape(Capsule())
    }

    @ViewBuilder
    private func renameDeviceSheet(_ device: PairedDevice) -> some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text("Rename device alias for \(device.device_code).")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                TextField("Alias", text: $renameAliasText)
                    .textFieldStyle(.roundedBorder)

                Button("Save Alias") {
                    Task {
                        let ok = await session.updateDeviceAlias(deviceID: device.id, alias: renameAliasText)
                        if ok {
                            assistantMessage = "Device alias updated."
                            renameDeviceTarget = nil
                        }
                    }
                }
                .buttonStyle(LiquidPrimaryButtonStyle())

                Spacer()
            }
            .padding(16)
            .navigationTitle("Rename Device")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        renameDeviceTarget = nil
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func networkProfileSheet(_ device: PairedDevice) -> some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text("Push Wi-Fi profile to \(device.device_code).")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                TextField("SSID", text: $networkSSIDText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .textFieldStyle(.roundedBorder)

                SecureField("Password", text: $networkPasswordText)
                    .textFieldStyle(.roundedBorder)

                Button("Push Network Profile") {
                    Task {
                        let ok = await session.queueDeviceNetworkProfile(
                            deviceID: device.id,
                            ssid: networkSSIDText,
                            password: networkPasswordText
                        )
                        if ok {
                            assistantMessage = "Network profile queued for \(device.device_code)."
                            networkProfileTarget = nil
                        }
                    }
                }
                .buttonStyle(LiquidPrimaryButtonStyle())
                .disabled(networkSSIDText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                Spacer()
            }
            .padding(16)
            .navigationTitle("Network Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        networkProfileTarget = nil
                    }
                }
            }
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
            .onDisappear {
                ble.stopScanning()
                ble.disconnect()
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Find your ESP32 device over Bluetooth, then pair it with your account.")
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
}
