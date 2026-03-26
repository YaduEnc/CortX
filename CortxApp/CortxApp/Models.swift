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

struct AppTokenResponse: Decodable {
    let access_token: String
    let token_type: String
    let expires_in_minutes: Int
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

    var id: String { device_id }
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
        status.lowercased() == "done" && has_audio
    }
}

struct AppCaptureTranscript: Decodable {
    let session_id: String
    let model_name: String
    let language: String?
    let full_text: String
    let duration_seconds: Double?
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
