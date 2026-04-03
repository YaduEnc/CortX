import Foundation

struct APIErrorResponse: Decodable {
    let detail: String
}

struct AuthRequest: Encodable {
    let email: String
    let password: String
}

struct RegisterRequest: Encodable {
    let email: String
    let password: String
    let full_name: String?
}

struct ForgotPasswordRequest: Encodable {
    let email: String
}

struct ForgotPasswordConfirmRequest: Encodable {
    let email: String
    let reset_token: String
    let new_password: String
}

struct DeleteAccountRequest: Encodable {
    let password: String
}

struct AppMeUpdateRequest: Encodable {
    let full_name: String?
}

struct AppTokenResponse: Decodable {
    let access_token: String
    let token_type: String
    let expires_in_minutes: Int
}

struct AppActionStatusResponse: Decodable {
    let status: String
    let message: String
}

struct ForgotPasswordRequestResponse: Decodable {
    let status: String
    let message: String
    let expires_in_seconds: Int?
    let reset_token: String?
}

struct AppMeResponse: Decodable {
    let user_id: String
    let email: String
    let full_name: String?
    let created_at: Date
}

struct AppUserPreferences: Decodable {
    let timezone: String
    let daily_summary_enabled: Bool
    let reminder_notifications_enabled: Bool
    let calendar_export_default_enabled: Bool
    let updated_at: Date
}

struct AppUserPreferencesUpdateRequest: Encodable {
    let timezone: String?
    let daily_summary_enabled: Bool?
    let reminder_notifications_enabled: Bool?
    let calendar_export_default_enabled: Bool?
}

struct PairingStartRequest: Encodable {
    let device_code: String
    let pair_nonce: String
}

struct PairingStartResponse: Decodable {
    let pairing_session_id: String
    let pair_token: String
    let expires_at: Date
}

struct PairedDevice: Decodable, Identifiable {
    let device_id: String
    let device_code: String
    let alias: String?
    let paired_at: Date
    let last_seen_at: Date?
    let status: String
    let firmware_version: String?
    let last_capture_at: Date?

    var id: String { device_id }
}

struct AppDeviceUpdateRequest: Encodable {
    let alias: String?
}

struct AppQueueNetworkProfileRequest: Encodable {
    let ssid: String
    let password: String
    let source: String
}

struct AppQueueNetworkProfileResponse: Decodable {
    let status: String
    let expires_in_seconds: Int
}

struct AppCaptureSession: Decodable, Identifiable {
    let session_id: String
    let device_id: String
    let device_code: String
    let status: String
    let total_chunks: Int
    let started_at: Date
    let finalized_at: Date?
    let duration_seconds: Double?
    let has_audio: Bool

    var id: String { session_id }

    var isPlayable: Bool {
        has_audio
    }

    var playbackAvailabilityLabel: String {
        if has_audio {
            return "Audio Ready"
        }
        return status.capitalized
    }
}

struct AppCaptureTranscript: Decodable {
    let session_id: String
    let model_name: String
    let language: String?
    let full_text: String
    let duration_seconds: Double?
}

struct AppCaptureUploadResponse: Decodable {
    let session_id: String
    let status: String
    let queued_for_transcription: Bool
    let audio_size_bytes: Int
    let sample_rate: Int
    let channels: Int
    let codec: String
}

struct AppAssistantItem: Decodable, Identifiable {
    let item_id: String
    let extraction_id: String
    let session_id: String
    let transcript_id: String
    let item_type: String
    let title: String
    let details: String?
    let due_at: Date?
    let timezone: String?
    let priority: Int?
    let status: String
    let source_segment_start_seconds: Double?
    let source_segment_end_seconds: Double?
    let created_at: Date
    let updated_at: Date
    let completed_at: Date?

    var id: String { item_id }
}

struct AppCaptureAIExtraction: Decodable {
    let extraction_id: String
    let session_id: String
    let transcript_id: String
    let status: String
    let intent: String?
    let intent_confidence: Double?
    let summary: String?
    let plan_steps: [AppAssistantPlanStep]
    let model_name: String?
    let error_message: String?
    let created_at: Date
    let started_at: Date?
    let completed_at: Date?
    let updated_at: Date
}

struct AppAssistantPlanStep: Decodable, Identifiable {
    let item_type: String?
    let title: String
    let details: String?
    let due_at: Date?
    let timezone: String?
    let priority: Int?
    let status: String?
    let source_segment_start_seconds: Double?
    let source_segment_end_seconds: Double?

    var id: String {
        "\(title)|\(details ?? "")|\(due_at?.timeIntervalSince1970 ?? 0)"
    }
}

struct AppCaptureAIResponse: Decodable {
    let session_id: String
    let transcript_ready: Bool
    let extraction: AppCaptureAIExtraction?
    let items: [AppAssistantItem]
}

struct AppAssistantItemUpdateRequest: Encodable {
    let status: String?
    let due_at: Date?
    let timezone: String?
    let snooze_minutes: Int?
}

struct AppCaptureAIReprocessResponse: Decodable {
    let session_id: String
    let extraction_id: String
    let status: String
    let queued: Bool
}

struct DashboardDailySummaryMetrics: Decodable {
    let memories_count: Int
    let transcript_ready_count: Int
    let open_actions_due_count: Int
    let upcoming_events_count: Int
    let top_intent: String?
    let device_count: Int
}

struct DashboardDailySummaryFocusItem: Decodable, Identifiable {
    let item_id: String
    let item_type: String
    let title: String
    let due_at: Date?
    let status: String
    let session_id: String
    let device_code: String?

    var id: String { item_id }
}

struct DashboardDailySummaryDeviceBreakdown: Decodable, Identifiable {
    let device_id: String
    let device_code: String
    let memories_count: Int
    let transcript_ready_count: Int
    let open_action_count: Int
    let upcoming_event_count: Int

    var id: String { device_id }
}

struct DashboardDailySummary: Decodable {
    let date: String
    let timezone: String
    let headline: String
    let generated_at: Date
    let metrics: DashboardDailySummaryMetrics
    let focus_items: [DashboardDailySummaryFocusItem]
    let device_breakdown: [DashboardDailySummaryDeviceBreakdown]
}

enum PairingStatus: String {
    case idle
    case pairing_mode
    case token_received
    case validating
    case pending
    case success
    case failed
    case expired
    case unknown

    init(rawValueOrUnknown raw: String) {
        self = PairingStatus(rawValue: raw.lowercased()) ?? .unknown
    }

    var userLabel: String {
        switch self {
        case .idle: return "Idle"
        case .pairing_mode: return "Pairing mode"
        case .token_received: return "Token received"
        case .validating: return "Validating token"
        case .pending: return "Pending"
        case .success: return "Paired successfully"
        case .failed: return "Pairing failed"
        case .expired: return "Pairing expired"
        case .unknown: return "Unknown status"
        }
    }
}

struct BLEDeviceInfo {
    let deviceCode: String
    let firmwareVersion: String?
    let rawPayload: String
}

// MARK: - Idea Graph Models

struct IdeaGraphEntity: Decodable, Identifiable, Hashable {
    let entity_id: String
    let entity_type: String
    let name: String
    let mention_count: Int
    let first_seen_at: Date
    let last_seen_at: Date

    var id: String { entity_id }

    func hash(into hasher: inout Hasher) {
        hasher.combine(entity_id)
    }

    static func == (lhs: IdeaGraphEntity, rhs: IdeaGraphEntity) -> Bool {
        lhs.entity_id == rhs.entity_id
    }

    var typeColor: String {
        switch entity_type {
        case "person": return "person"
        case "project": return "project"
        case "topic": return "topic"
        case "place": return "place"
        case "organization": return "organization"
        default: return "topic"
        }
    }

    var typeIcon: String {
        switch entity_type {
        case "person": return "person.fill"
        case "project": return "folder.fill"
        case "topic": return "lightbulb.fill"
        case "place": return "mappin.circle.fill"
        case "organization": return "building.2.fill"
        default: return "tag.fill"
        }
    }
}

struct IdeaGraphConnection: Decodable, Identifiable {
    let source_entity_id: String
    let source_name: String
    let source_type: String
    let target_entity_id: String
    let target_name: String
    let target_type: String
    let shared_session_count: Int
    let shared_session_ids: [String]

    var id: String { "\(source_entity_id)-\(target_entity_id)" }
}

struct IdeaGraphResponse: Decodable {
    let nodes: [IdeaGraphEntity]
    let edges: [IdeaGraphConnection]
    let total_entities: Int
    let total_connections: Int
}

struct IdeaGraphMention: Decodable, Identifiable {
    let mention_id: String
    let entity_id: String
    let entity_name: String
    let entity_type: String
    let session_id: String
    let context_snippet: String?
    let confidence: Double?
    let created_at: Date

    var id: String { mention_id }
}
