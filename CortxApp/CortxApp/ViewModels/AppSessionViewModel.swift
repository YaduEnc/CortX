import Foundation
import Combine

@MainActor
final class AppSessionViewModel: ObservableObject {
    @Published var isBootstrapping = true
    @Published var isWorking = false
    @Published var isAuthenticated = false
    @Published var errorMessage: String?
    @Published var pairedDevices: [PairedDevice] = []
    @Published var captures: [AppCaptureSession] = []
    @Published var userEmail: String = ""

    private let apiClient: APIClient
    private let tokenStore: KeychainTokenStore
    private var accessToken: String?
    private var didBootstrap = false

    init(apiClient: APIClient? = nil, tokenStore: KeychainTokenStore? = nil) {
        self.apiClient = apiClient ?? APIClient()
        self.tokenStore = tokenStore ?? KeychainTokenStore()
    }

    func bootstrapIfNeeded() {
        guard !didBootstrap else { return }
        didBootstrap = true

        accessToken = tokenStore.load()
        userEmail = UserDefaults.standard.string(forKey: "last_user_email") ?? ""
        isAuthenticated = accessToken != nil

        guard accessToken != nil else {
            isBootstrapping = false
            return
        }

        Task {
            await refreshPairedDevices(showLoader: false)
            await refreshCaptures(showLoader: false)
            isBootstrapping = false
        }
    }

    func register(email: String, password: String, fullName: String?) async {
        guard validate(email: email, password: password) else { return }
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }

        do {
            let tokenResponse = try await apiClient.register(email: email, password: password, fullName: fullName)
            completeLogin(token: tokenResponse.access_token, email: email)
            await refreshPairedDevices(showLoader: false)
            await refreshCaptures(showLoader: false)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func login(email: String, password: String) async {
        guard validate(email: email, password: password) else { return }
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }

        do {
            let tokenResponse = try await apiClient.login(email: email, password: password)
            completeLogin(token: tokenResponse.access_token, email: email)
            await refreshPairedDevices(showLoader: false)
            await refreshCaptures(showLoader: false)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshPairedDevices(showLoader: Bool = true) async {
        guard let token = accessToken else {
            pairedDevices = []
            isAuthenticated = false
            isBootstrapping = false
            return
        }

        if showLoader {
            isWorking = true
        }
        defer {
            if showLoader {
                isWorking = false
            }
        }

        do {
            pairedDevices = try await apiClient.listPairedDevices(accessToken: token)
            errorMessage = nil
        } catch let error as APIClientError {
            if case .unauthorized = error {
                logout()
                errorMessage = "Session expired. Please log in again."
            } else {
                errorMessage = error.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logout() {
        accessToken = nil
        tokenStore.clear()
        isAuthenticated = false
        pairedDevices = []
        captures = []
    }

    func refreshCaptures(showLoader: Bool = true) async {
        guard let token = accessToken else {
            captures = []
            return
        }

        if showLoader {
            isWorking = true
        }
        defer {
            if showLoader {
                isWorking = false
            }
        }

        do {
            captures = try await apiClient.listCaptures(accessToken: token)
            errorMessage = nil
        } catch let error as APIClientError {
            if case .unauthorized = error {
                logout()
                errorMessage = "Session expired. Please log in again."
            } else {
                errorMessage = error.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func fetchAudio(sessionID: String) async throws -> Data {
        guard let token = accessToken else {
            throw APIClientError.unauthorized
        }
        return try await apiClient.downloadCaptureAudio(sessionID: sessionID, accessToken: token)
    }

    func fetchTranscript(sessionID: String) async throws -> AppCaptureTranscript {
        guard let token = accessToken else {
            throw APIClientError.unauthorized
        }
        return try await apiClient.getCaptureTranscript(sessionID: sessionID, accessToken: token)
    }

    func pairingAccessToken() -> String? {
        accessToken
    }

    func api() -> APIClient {
        apiClient
    }

    private func completeLogin(token: String, email: String) {
        accessToken = token
        _ = tokenStore.save(token: token)
        isAuthenticated = true
        userEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        UserDefaults.standard.set(userEmail, forKey: "last_user_email")
        errorMessage = nil
        isBootstrapping = false
    }

    private func validate(email: String, password: String) -> Bool {
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalizedEmail.isEmpty || !normalizedEmail.contains("@") {
            errorMessage = "Enter a valid email address."
            return false
        }
        if password.count < 8 {
            errorMessage = "Password must be at least 8 characters."
            return false
        }
        return true
    }
}
