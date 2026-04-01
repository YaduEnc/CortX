import SwiftUI

struct AuthView: View {
    enum Mode: String, CaseIterable {
        case login = "Login"
        case signup = "Sign Up"
    }

    @ObservedObject var session: AppSessionViewModel

    @State private var mode: Mode = .login
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var showPassword = false
    @State private var reveal = false
    @State private var showForgotPasswordSheet = false

    var body: some View {
        ZStack {
            AppBackgroundView()

            ScrollView(showsIndicators: false) {
                VStack(spacing: 20) {
                    VStack(spacing: 10) {
                        Image(systemName: "brain.filled.head.profile")
                            .font(.system(size: 34, weight: .semibold))
                            .foregroundStyle(Color(red: 0.10, green: 0.53, blue: 0.95))
                            .padding(14)
                            .background(
                                Circle()
                                    .fill(Color.white.opacity(0.5))
                            )
                        Text("SecondMind")
                            .font(.system(size: 38, weight: .heavy, design: .rounded))
                            .foregroundStyle(Color.primary)
                        Text("Cognitive OS for your thinking")
                            .font(.system(.subheadline, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 26)

                    VStack(spacing: 14) {
                        Picker("Auth Mode", selection: $mode) {
                            ForEach(Mode.allCases, id: \.self) { current in
                                Text(current.rawValue).tag(current)
                            }
                        }
                        .pickerStyle(.segmented)
                        .onChange(of: mode) { _, _ in
                            withAnimation(.spring(response: 0.35, dampingFraction: 0.9)) {
                                session.errorMessage = nil
                            }
                        }

                        VStack(spacing: 12) {
                            if mode == .signup {
                                TextField("Full name (optional)", text: $fullName)
                                    .textContentType(.name)
                                    .liquidInput()
                                    .transition(.move(edge: .top).combined(with: .opacity))
                            }

                            TextField("Email", text: $email)
                                .textContentType(.emailAddress)
                                .keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .liquidInput()

                            Group {
                                if showPassword {
                                    TextField("Password", text: $password)
                                        .textContentType(.password)
                                } else {
                                    SecureField("Password", text: $password)
                                        .textContentType(.password)
                                }
                            }
                            .liquidInput()

                            Toggle("Show password", isOn: $showPassword)
                                .font(.system(.footnote, design: .rounded))
                                .tint(Color(red: 0.10, green: 0.53, blue: 0.95))
                        }

                        if let error = session.errorMessage {
                            Text(error)
                                .font(.system(.footnote, design: .rounded))
                                .foregroundStyle(.red)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .transition(.opacity)
                        }

                        Button {
                            Task {
                                if mode == .login {
                                    await session.login(email: email, password: password)
                                } else {
                                    await session.register(email: email, password: password, fullName: fullName)
                                }
                            }
                        } label: {
                            HStack(spacing: 8) {
                                if session.isWorking {
                                    ProgressView()
                                        .tint(.white)
                                }
                                Text(mode == .login ? "Continue to Dashboard" : "Create Account")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(LiquidPrimaryButtonStyle())
                        .disabled(session.isWorking)

                        if mode == .login {
                            Button("Forgot Password?") {
                                showForgotPasswordSheet = true
                            }
                            .font(.system(.footnote, design: .rounded))
                            .foregroundStyle(Color(red: 0.10, green: 0.53, blue: 0.95))
                            .disabled(session.isWorking)
                        }
                    }
                    .padding(18)
                    .liquidCard()
                    .padding(.horizontal, 16)
                }
                .opacity(reveal ? 1 : 0)
                .offset(y: reveal ? 0 : 14)
                .animation(.easeOut(duration: 0.5), value: reveal)
                .padding(.bottom, 24)
            }
        }
        .onAppear {
            reveal = true
        }
        .sheet(isPresented: $showForgotPasswordSheet) {
            ForgotPasswordSheet(
                session: session,
                initialEmail: email
            ) { updatedEmail in
                email = updatedEmail
                password = ""
                mode = .login
            }
        }
    }
}

struct ForgotPasswordSheet: View {
    @Environment(\.dismiss) private var dismiss

    @ObservedObject var session: AppSessionViewModel
    let initialEmail: String
    let onResetSuccess: (String) -> Void

    @State private var email = ""
    @State private var resetToken = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var infoMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Request a reset token, then set a new password.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .liquidInput()

                    Button {
                        Task {
                            await requestToken()
                        }
                    } label: {
                        if session.isWorking {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text("Send Reset Token")
                        }
                    }
                    .buttonStyle(LiquidPrimaryButtonStyle())
                    .disabled(session.isWorking)

                    TextField("Reset token", text: $resetToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .liquidInput()

                    SecureField("New password", text: $newPassword)
                        .textContentType(.newPassword)
                        .liquidInput()

                    SecureField("Confirm new password", text: $confirmPassword)
                        .textContentType(.newPassword)
                        .liquidInput()

                    Button {
                        Task {
                            await confirmReset()
                        }
                    } label: {
                        if session.isWorking {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text("Reset Password")
                        }
                    }
                    .buttonStyle(LiquidPrimaryButtonStyle())
                    .disabled(session.isWorking)

                    if let infoMessage {
                        Text(infoMessage)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    if let error = session.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }
                .padding(16)
            }
            .navigationTitle("Forgot Password")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        dismiss()
                    }
                }
            }
            .onAppear {
                email = initialEmail.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            }
        }
    }

    private func requestToken() async {
        guard let response = await session.requestPasswordReset(email: email) else {
            return
        }

        var lines: [String] = [response.message]
        if let expires = response.expires_in_seconds {
            lines.append("Expires in \(expires / 60) min.")
        }
        if let token = response.reset_token, !token.isEmpty {
            resetToken = token
            lines.append("Reset token auto-filled (development mode).")
        }
        infoMessage = lines.joined(separator: " ")
    }

    private func confirmReset() async {
        if newPassword != confirmPassword {
            infoMessage = nil
            session.errorMessage = "Password confirmation does not match."
            return
        }

        let success = await session.confirmPasswordReset(
            email: email,
            resetToken: resetToken,
            newPassword: newPassword
        )
        guard success else { return }

        onResetSuccess(email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
        dismiss()
    }
}

private extension View {
    func liquidInput() -> some View {
        self
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white.opacity(0.36))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(Color.white.opacity(0.5), lineWidth: 1)
                    )
            )
            .font(.system(.body, design: .rounded))
    }
}
