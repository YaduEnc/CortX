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
    @Published var userFullName: String?

    private let apiClient: APIClient
    private let tokenStore: KeychainTokenStore
    private var accessToken: String?
    private var didBootstrap = false
    private let lastUserEmailKey = "last_user_email"
    private let lastUserFullNameKey = "last_user_full_name"

    init(apiClient: APIClient? = nil, tokenStore: KeychainTokenStore? = nil) {
        self.apiClient = apiClient ?? APIClient()
        self.tokenStore = tokenStore ?? KeychainTokenStore()
    }

    func bootstrapIfNeeded() {
        guard !didBootstrap else { return }
        didBootstrap = true

        accessToken = tokenStore.load()
        userEmail = UserDefaults.standard.string(forKey: lastUserEmailKey) ?? ""
        userFullName = UserDefaults.standard.string(forKey: lastUserFullNameKey)
        isAuthenticated = accessToken != nil

        guard accessToken != nil else {
            isBootstrapping = false
            return
        }

        Task {
            await refreshCurrentUser(showLoader: false)
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
            await refreshCurrentUser(showLoader: false)
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
            await refreshCurrentUser(showLoader: false)
            await refreshPairedDevices(showLoader: false)
            await refreshCaptures(showLoader: false)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func requestPasswordReset(email: String) async -> ForgotPasswordRequestResponse? {
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalizedEmail.isEmpty, normalizedEmail.contains("@") else {
            errorMessage = "Enter a valid email address."
            return nil
        }

        isWorking = true
        errorMessage = nil
        defer { isWorking = false }

        do {
            let response = try await apiClient.requestPasswordReset(email: normalizedEmail)
            errorMessage = nil
            return response
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func confirmPasswordReset(email: String, resetToken: String, newPassword: String) async -> Bool {
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedEmail.isEmpty || !normalizedEmail.contains("@") {
            errorMessage = "Enter a valid email address."
            return false
        }
        if resetToken.trimmingCharacters(in: .whitespacesAndNewlines).count < 12 {
            errorMessage = "Reset token looks invalid."
            return false
        }
        if newPassword.count < 8 {
            errorMessage = "Password must be at least 8 characters."
            return false
        }

        isWorking = true
        errorMessage = nil
        defer { isWorking = false }

        do {
            _ = try await apiClient.confirmPasswordReset(
                email: normalizedEmail,
                resetToken: resetToken,
                newPassword: newPassword
            )
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func deleteAccount(password: String) async -> Bool {
        guard let token = accessToken else {
            errorMessage = "Session expired. Please log in again."
            return false
        }
        if password.count < 8 {
            errorMessage = "Enter your current password."
            return false
        }

        isWorking = true
        errorMessage = nil
        defer { isWorking = false }

        do {
            _ = try await apiClient.deleteCurrentAccount(password: password, accessToken: token)
            logout()
            userEmail = ""
            UserDefaults.standard.removeObject(forKey: lastUserEmailKey)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func refreshCurrentUser(showLoader: Bool = true) async {
        guard let token = accessToken else {
            userFullName = nil
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
            let me = try await apiClient.getCurrentUser(accessToken: token)
            userEmail = me.email
            userFullName = me.full_name?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
            UserDefaults.standard.set(userEmail, forKey: lastUserEmailKey)
            if let userFullName {
                UserDefaults.standard.set(userFullName, forKey: lastUserFullNameKey)
            } else {
                UserDefaults.standard.removeObject(forKey: lastUserFullNameKey)
            }
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
        userFullName = nil
        UserDefaults.standard.removeObject(forKey: lastUserFullNameKey)
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

    var userDisplayName: String {
        if let userFullName, !userFullName.isEmpty {
            return userFullName
        }
        return userEmail
    }

    var shouldShowEmailAsSubtitle: Bool {
        guard let userFullName, !userFullName.isEmpty else {
            return false
        }
        return !userEmail.isEmpty
    }

    private func completeLogin(token: String, email: String) {
        accessToken = token
        _ = tokenStore.save(token: token)
        isAuthenticated = true
        userEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        UserDefaults.standard.set(userEmail, forKey: lastUserEmailKey)
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

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
