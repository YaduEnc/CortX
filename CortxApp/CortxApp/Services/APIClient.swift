import Foundation

enum APIClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case server(String)
    case decoding
    case encoding

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL."
        case .invalidResponse:
            return "Invalid server response."
        case .unauthorized:
            return "Session expired. Please log in again."
        case let .server(message):
            return message
        case .decoding:
            return "Unable to parse server response."
        case .encoding:
            return "Unable to encode request."
        }
    }
}

final class APIClient {
    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL = AppConfig.apiBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            if let date = ISO8601DateFormatter.withFractional.date(from: value) {
                return date
            }
            if let date = ISO8601DateFormatter.defaultInternet.date(from: value) {
                return date
            }
            throw APIClientError.decoding
        }
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder
    }

    func register(email: String, password: String, fullName: String?) async throws -> AppTokenResponse {
        let body = RegisterRequest(
            email: email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            password: password,
            full_name: fullName?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        )
        return try await send(path: "app/register", method: "POST", body: body, bearerToken: nil)
    }

    func login(email: String, password: String) async throws -> AppTokenResponse {
        let body = AuthRequest(
            email: email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            password: password
        )
        return try await send(path: "app/auth", method: "POST", body: body, bearerToken: nil)
    }

    func requestPasswordReset(email: String) async throws -> ForgotPasswordRequestResponse {
        let body = ForgotPasswordRequest(
            email: email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        )
        return try await send(path: "app/password/forgot/request", method: "POST", body: body, bearerToken: nil)
    }

    func confirmPasswordReset(email: String, resetToken: String, newPassword: String) async throws -> AppActionStatusResponse {
        let body = ForgotPasswordConfirmRequest(
            email: email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            reset_token: resetToken.trimmingCharacters(in: .whitespacesAndNewlines),
            new_password: newPassword
        )
        return try await send(path: "app/password/forgot/confirm", method: "POST", body: body, bearerToken: nil)
    }

    func getCurrentUser(accessToken: String) async throws -> AppMeResponse {
        try await send(path: "app/me", method: "GET", bearerToken: accessToken)
    }

    func updateCurrentUser(fullName: String?, accessToken: String) async throws -> AppMeResponse {
        let body = AppMeUpdateRequest(full_name: fullName?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty)
        return try await send(path: "app/me", method: "PATCH", body: body, bearerToken: accessToken)
    }

    func getUserPreferences(accessToken: String) async throws -> AppUserPreferences {
        try await send(path: "app/me/preferences", method: "GET", bearerToken: accessToken)
    }

    func updateUserPreferences(payload: AppUserPreferencesUpdateRequest, accessToken: String) async throws -> AppUserPreferences {
        try await send(path: "app/me/preferences", method: "PATCH", body: payload, bearerToken: accessToken)
    }

    func deleteCurrentAccount(password: String, accessToken: String) async throws -> AppActionStatusResponse {
        let body = DeleteAccountRequest(password: password)
        return try await send(path: "app/me/delete", method: "POST", body: body, bearerToken: accessToken)
    }

    func listPairedDevices(accessToken: String) async throws -> [PairedDevice] {
        try await send(path: "app/devices", method: "GET", bearerToken: accessToken)
    }

    func updatePairedDevice(deviceID: String, alias: String?, accessToken: String) async throws -> PairedDevice {
        let body = AppDeviceUpdateRequest(alias: alias?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty)
        return try await send(path: "app/devices/\(deviceID)", method: "PATCH", body: body, bearerToken: accessToken)
    }

    func unpairDevice(deviceID: String, accessToken: String) async throws -> AppActionStatusResponse {
        try await send(path: "app/devices/\(deviceID)", method: "DELETE", body: Optional<String>.none, bearerToken: accessToken)
    }

    func queueDeviceNetworkProfile(
        deviceID: String,
        ssid: String,
        password: String,
        source: String = "app_manual",
        accessToken: String
    ) async throws -> AppQueueNetworkProfileResponse {
        let body = AppQueueNetworkProfileRequest(
            ssid: ssid.trimmingCharacters(in: .whitespacesAndNewlines),
            password: password,
            source: source
        )
        return try await send(path: "app/devices/\(deviceID)/network-profile", method: "POST", body: body, bearerToken: accessToken)
    }

    func startPairing(deviceCode: String, pairNonce: String, accessToken: String) async throws -> PairingStartResponse {
        let body = PairingStartRequest(device_code: deviceCode, pair_nonce: pairNonce)
        return try await send(path: "pairing/start", method: "POST", body: body, bearerToken: accessToken)
    }

    func listCaptures(accessToken: String, limit: Int = 30) async throws -> [AppCaptureSession] {
        let clamped = max(1, min(limit, 100))
        return try await send(path: "app/captures?limit=\(clamped)", method: "GET", bearerToken: accessToken)
    }

    func getCaptureTranscript(sessionID: String, accessToken: String) async throws -> AppCaptureTranscript {
        try await send(path: "app/captures/\(sessionID)/transcript", method: "GET", bearerToken: accessToken)
    }

    func uploadAppCaptureWAV(
        wavData: Data,
        sampleRate: Int = 16_000,
        channels: Int = 1,
        codec: String = "pcm16le",
        accessToken: String
    ) async throws -> AppCaptureUploadResponse {
        guard let url = buildURL(path: "app/captures/upload-wav") else {
            throw APIClientError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.httpBody = wavData
        request.setValue("audio/wav", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue(String(sampleRate), forHTTPHeaderField: "X-Sample-Rate")
        request.setValue(String(channels), forHTTPHeaderField: "X-Channels")
        request.setValue(codec, forHTTPHeaderField: "X-Codec")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }
        if http.statusCode == 401 {
            throw APIClientError.unauthorized
        }
        guard (200...299).contains(http.statusCode) else {
            if let apiError = try? decoder.decode(APIErrorResponse.self, from: data) {
                throw APIClientError.server(apiError.detail)
            }
            throw APIClientError.server("Request failed with status \(http.statusCode)")
        }

        do {
            return try decoder.decode(AppCaptureUploadResponse.self, from: data)
        } catch {
            throw APIClientError.decoding
        }
    }

    func downloadCaptureAudio(sessionID: String, accessToken: String) async throws -> Data {
        let (data, _) = try await rawRequest(
            path: "app/captures/\(sessionID)/audio",
            method: "GET",
            bearerToken: accessToken
        )
        return data
    }

    func getCaptureAI(sessionID: String, accessToken: String) async throws -> AppCaptureAIResponse {
        try await send(path: "app/captures/\(sessionID)/ai", method: "GET", bearerToken: accessToken)
    }

    func listAssistantItems(
        accessToken: String,
        itemType: String? = nil,
        itemStatus: String? = nil,
        limit: Int = 60
    ) async throws -> [AppAssistantItem] {
        let clamped = max(1, min(limit, 200))
        var queryParts = ["limit=\(clamped)"]
        if let itemType, !itemType.isEmpty {
            queryParts.append("item_type=\(itemType.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? itemType)")
        }
        if let itemStatus, !itemStatus.isEmpty {
            queryParts.append("item_status=\(itemStatus.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? itemStatus)")
        }
        let query = queryParts.joined(separator: "&")
        return try await send(path: "app/assistant/items?\(query)", method: "GET", bearerToken: accessToken)
    }

    func updateAssistantItem(
        itemID: String,
        payload: AppAssistantItemUpdateRequest,
        accessToken: String
    ) async throws -> AppAssistantItem {
        try await send(path: "app/assistant/items/\(itemID)", method: "PATCH", body: payload, bearerToken: accessToken)
    }

    func reprocessCaptureAI(sessionID: String, accessToken: String) async throws -> AppCaptureAIReprocessResponse {
        try await send(path: "app/captures/\(sessionID)/ai/reprocess", method: "POST", body: Optional<String>.none, bearerToken: accessToken)
    }

    func getDashboardDailySummary(
        accessToken: String,
        date: String? = nil,
        timezone: String,
        deviceID: String? = nil
    ) async throws -> DashboardDailySummary {
        var queryParts: [String] = []
        if let date, !date.isEmpty {
            queryParts.append("date=\(date)")
        }
        let tzEncoded = timezone.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? timezone
        queryParts.append("tz=\(tzEncoded)")
        if let deviceID, !deviceID.isEmpty {
            queryParts.append("device_id=\(deviceID)")
        }
        let query = queryParts.joined(separator: "&")
        return try await send(path: "app/dashboard/daily-summary?\(query)", method: "GET", bearerToken: accessToken)
    }

    // MARK: - Idea Graph

    func fetchIdeaGraph(
        accessToken: String,
        entityType: String? = nil,
        minMentions: Int = 1,
        limit: Int = 100
    ) async throws -> IdeaGraphResponse {
        var queryParts = ["limit=\(max(1, min(limit, 500)))", "min_mentions=\(minMentions)"]
        if let entityType, !entityType.isEmpty {
            queryParts.append("entity_type=\(entityType.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? entityType)")
        }
        let query = queryParts.joined(separator: "&")
        return try await send(path: "app/idea-graph?\(query)", method: "GET", bearerToken: accessToken)
    }

    func fetchEntityMentions(
        entityID: String,
        accessToken: String,
        limit: Int = 50
    ) async throws -> [IdeaGraphMention] {
        try await send(path: "app/idea-graph/entities/\(entityID)/mentions?limit=\(limit)", method: "GET", bearerToken: accessToken)
    }

    private func send<Body: Encodable, Response: Decodable>(
        path: String,
        method: String,
        body: Body?,
        bearerToken: String?
    ) async throws -> Response {
        guard let url = buildURL(path: path) else {
            throw APIClientError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let bearerToken {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }

        if let body {
            do {
                request.httpBody = try encoder.encode(body)
            } catch {
                throw APIClientError.encoding
            }
        }

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }

        if http.statusCode == 401 {
            throw APIClientError.unauthorized
        }

        guard (200...299).contains(http.statusCode) else {
            if let apiError = try? decoder.decode(APIErrorResponse.self, from: data) {
                throw APIClientError.server(apiError.detail)
            }
            throw APIClientError.server("Request failed with status \(http.statusCode)")
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIClientError.decoding
        }
    }

    private func send<Response: Decodable>(
        path: String,
        method: String,
        bearerToken: String?
    ) async throws -> Response {
        try await send(path: path, method: method, body: Optional<String>.none, bearerToken: bearerToken)
    }

    private func rawRequest(
        path: String,
        method: String,
        bearerToken: String?
    ) async throws -> (Data, HTTPURLResponse) {
        guard let url = buildURL(path: path) else {
            throw APIClientError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        if let bearerToken {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }

        if http.statusCode == 401 {
            throw APIClientError.unauthorized
        }
        guard (200...299).contains(http.statusCode) else {
            if let apiError = try? decoder.decode(APIErrorResponse.self, from: data) {
                throw APIClientError.server(apiError.detail)
            }
            throw APIClientError.server("Request failed with status \(http.statusCode)")
        }

        return (data, http)
    }

    private func buildURL(path: String) -> URL? {
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        return URL(string: base + path)
    }
}

private extension ISO8601DateFormatter {
    static let withFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    static let defaultInternet: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
