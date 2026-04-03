import SwiftUI

struct MemoryDetailSheet: View {
    let capture: AppCaptureSession
    let transcript: AppCaptureTranscript?
    let transcriptError: String?
    let extraction: AppCaptureAIExtraction?
    let items: [AppAssistantItem]
    let aiError: String?
    let isTranscriptLoading: Bool
    let isAILoading: Bool
    let isPlaying: Bool

    let onPlay: () -> Void
    let onLoadTranscript: () -> Void
    let onLoadAI: () -> Void
    let onReprocess: () -> Void
    let onRefreshAll: () -> Void
    let onSetItemStatus: (AppAssistantItem, String) -> Void
    let onSnooze: (AppAssistantItem, Int) -> Void
    let onAddToCalendar: (AppAssistantItem) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var showFullTranscript = false
    @State private var showAllActions = false
    @State private var showAllReminders = false

    private var actionItems: [AppAssistantItem] {
        items.filter { $0.item_type == "task" || $0.item_type == "plan_step" }
    }

    private var reminderItems: [AppAssistantItem] {
        items.filter { $0.item_type == "reminder" }
    }

    private var eventCandidates: [AppAssistantItem] {
        (reminderItems + actionItems).filter { $0.due_at != nil }
    }

    private var controlGridColumns: [GridItem] {
        [
            GridItem(.flexible(), spacing: 10),
            GridItem(.flexible(), spacing: 10)
        ]
    }

    private var displayedActionItems: [AppAssistantItem] {
        showAllActions ? actionItems : Array(actionItems.prefix(3))
    }

    private var displayedReminderItems: [AppAssistantItem] {
        showAllReminders ? reminderItems : Array(reminderItems.prefix(3))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    heroCard
                    aiSummaryCard
                    transcriptCard
                    actionPlanCard
                    remindersCard
                    calendarEventsCard
                }
                .padding(16)
                .padding(.bottom, 20)
            }
            .background(AppBackgroundView())
            .navigationTitle("Memory")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        dismiss()
                    } label: {
                        Label("Close", systemImage: "xmark")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        onRefreshAll()
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                }
            }
        }
    }

    private var heroCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(capture.device_code)
                        .font(.system(size: 28, weight: .bold, design: .rounded))
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

            LazyVGrid(columns: controlGridColumns, spacing: 10) {
                memoryActionButton(
                    title: isPlaying ? "Playing" : "Play Memory",
                    icon: isPlaying ? "speaker.wave.2.fill" : "play.fill",
                    isPrimary: true,
                    isLoading: false,
                    isDisabled: !capture.isPlayable
                ) {
                    onPlay()
                }

                memoryActionButton(
                    title: "Transcript",
                    icon: "text.quote",
                    isPrimary: false,
                    isLoading: isTranscriptLoading,
                    isDisabled: false
                ) {
                    onLoadTranscript()
                }

                memoryActionButton(
                    title: "Load AI",
                    icon: "brain",
                    isPrimary: false,
                    isLoading: isAILoading,
                    isDisabled: false
                ) {
                    onLoadAI()
                }

                memoryActionButton(
                    title: "Reprocess",
                    icon: "sparkles",
                    isPrimary: false,
                    isLoading: false,
                    isDisabled: false
                ) {
                    onReprocess()
                }
            }
        }
        .padding(14)
        .memorySectionCard(accent: Color(red: 0.34, green: 0.72, blue: 0.95))
    }

    private var aiSummaryCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("AI Memory Brief")
                .font(.headline)

            Text(extraction?.summary?.isEmpty == false
                 ? (extraction?.summary ?? "")
                 : "AI summary is not ready. Tap AI to load or reprocess.")
            .font(.body)
            .foregroundStyle(.primary)

            if let intent = extraction?.intent, !intent.isEmpty {
                HStack(spacing: 8) {
                    detailChip("Intent: \(intent)", icon: "scope")
                    if let confidence = extraction?.intent_confidence {
                        detailChip("Confidence \(Int(confidence * 100))%", icon: "checkmark.seal")
                    }
                }
            } else if let aiError, !aiError.isEmpty {
                Text(aiError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .memorySectionCard(accent: Color(red: 0.52, green: 0.70, blue: 0.92))
    }

    private var transcriptCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Conversation Transcript")
                .font(.headline)

            if let transcript {
                let transcriptText = transcript.full_text.isEmpty ? "No speech detected." : transcript.full_text
                Text(transcriptText)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineLimit(showFullTranscript ? nil : 6)
                    .lineSpacing(2)
                    .textSelection(.enabled)

                Button(showFullTranscript ? "Show Less" : "Show More") {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showFullTranscript.toggle()
                    }
                }
                .buttonStyle(LiquidSecondaryButtonStyle())

                HStack(spacing: 8) {
                    if let language = transcript.language, !language.isEmpty {
                        detailChip("Lang: \(language)", icon: "globe")
                    }
                    detailChip("Model: \(transcript.model_name)", icon: "waveform")
                }
            } else if isTranscriptLoading {
                ProgressView("Loading transcript...")
            } else if let transcriptError, !transcriptError.isEmpty {
                Text(transcriptError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("Transcript not loaded yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .memorySectionCard(accent: Color(red: 0.42, green: 0.80, blue: 0.86))
    }

    private var actionPlanCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Intent Actions")
                .font(.headline)

            if actionItems.isEmpty {
                Text("No action items yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(displayedActionItems) { item in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(item.title)
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            Text(item.status.capitalized)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        if let details = item.details, !details.isEmpty {
                            Text(details)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        HStack(spacing: 8) {
                            if item.status == "done" {
                                Button("Reopen") {
                                    onSetItemStatus(item, "open")
                                }
                                .buttonStyle(LiquidSecondaryButtonStyleCompact())
                            } else {
                                Button("Complete") {
                                    onSetItemStatus(item, "done")
                                }
                                .buttonStyle(LiquidPrimaryButtonStyleCompact())

                                Button("Dismiss") {
                                    onSetItemStatus(item, "dismissed")
                                }
                                .buttonStyle(LiquidSecondaryButtonStyleCompact())
                            }
                        }
                    }
                    .padding(10)
                    .background(Color.white.opacity(0.16))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                if actionItems.count > 3 {
                    Button(showAllActions ? "Show Less Actions" : "Show All Actions (\(actionItems.count))") {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showAllActions.toggle()
                        }
                    }
                    .buttonStyle(LiquidSecondaryButtonStyleCompact())
                }
            }
        }
        .padding(14)
        .memorySectionCard(accent: Color(red: 0.50, green: 0.75, blue: 0.89))
    }

    private var remindersCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Reminders From Memory")
                .font(.headline)

            if reminderItems.isEmpty {
                Text("No reminders extracted from this memory.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(displayedReminderItems) { item in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(item.title)
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            Text(item.status.capitalized)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        if let dueAt = item.due_at {
                            Text("Due: \(dueAt.formatted(date: .abbreviated, time: .shortened))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let details = item.details, !details.isEmpty {
                            Text(details)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        HStack(spacing: 8) {
                            Button("Snooze 1h") {
                                onSnooze(item, 60)
                            }
                            .buttonStyle(LiquidSecondaryButtonStyleCompact())

                            Button("Add Event") {
                                onAddToCalendar(item)
                            }
                            .buttonStyle(LiquidPrimaryButtonStyleCompact())
                            .disabled(item.due_at == nil)

                            Button("Dismiss") {
                                onSetItemStatus(item, "dismissed")
                            }
                            .buttonStyle(LiquidSecondaryButtonStyleCompact())
                        }
                    }
                    .padding(10)
                    .background(Color.white.opacity(0.16))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                if reminderItems.count > 3 {
                    Button(showAllReminders ? "Show Less Reminders" : "Show All Reminders (\(reminderItems.count))") {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showAllReminders.toggle()
                        }
                    }
                    .buttonStyle(LiquidSecondaryButtonStyleCompact())
                }
            }
        }
        .padding(14)
        .memorySectionCard(accent: Color(red: 0.66, green: 0.76, blue: 0.92))
    }

    private var calendarEventsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Calendar Events")
                .font(.headline)

            if eventCandidates.isEmpty {
                Text("No dated events yet. Add due times in reminders/actions to generate calendar events.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(eventCandidates) { item in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title)
                                .font(.subheadline.weight(.semibold))
                            if let dueAt = item.due_at {
                                Text(dueAt.formatted(date: .abbreviated, time: .shortened))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Button("Add") {
                            onAddToCalendar(item)
                        }
                        .buttonStyle(LiquidPrimaryButtonStyleCompact())
                    }
                    .padding(10)
                    .background(Color.white.opacity(0.16))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
        }
        .padding(14)
        .memorySectionCard(accent: Color(red: 0.54, green: 0.79, blue: 0.95))
    }

    private func memoryActionButton(
        title: String,
        icon: String,
        isPrimary: Bool,
        isLoading: Bool,
        isDisabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if isLoading {
                    ProgressView()
                        .progressViewStyle(.circular)
                        .tint(isPrimary ? .white : .primary)
                        .scaleEffect(0.8)
                } else {
                    Image(systemName: icon)
                        .font(.system(size: 15, weight: .semibold))
                }

                Text(title)
                    .font(.system(.body, design: .rounded).weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .foregroundStyle(isPrimary ? .white : Color.primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(
                        isPrimary
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
                        : AnyShapeStyle(Color.white.opacity(0.22))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(isPrimary ? Color.white.opacity(0.3) : Color.white.opacity(0.38), lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .opacity(isDisabled ? 0.55 : 1)
        .disabled(isDisabled)
    }

    private func detailChip(_ text: String, icon: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
            Text(text)
        }
        .font(.caption2.weight(.semibold))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(Color.white.opacity(0.17))
        .clipShape(Capsule())
    }
}

private extension View {
    func memorySectionCard(accent: Color) -> some View {
        background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.20),
                            accent.opacity(0.16)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.48),
                            Color.white.opacity(0.18)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1
                )
        )
        .shadow(color: Color.black.opacity(0.08), radius: 16, x: 0, y: 10)
    }
}

private struct LiquidPrimaryButtonStyleCompact: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, design: .rounded).weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.10, green: 0.53, blue: 0.95),
                                Color(red: 0.03, green: 0.70, blue: 0.78)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(Color.white.opacity(0.3), lineWidth: 1)
                    )
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.88 : 1.0)
    }
}

private struct LiquidSecondaryButtonStyleCompact: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, design: .rounded).weight(.semibold))
            .foregroundStyle(Color.primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white.opacity(0.24))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(Color.white.opacity(0.44), lineWidth: 1)
                    )
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .opacity(configuration.isPressed ? 0.9 : 1.0)
    }
}
