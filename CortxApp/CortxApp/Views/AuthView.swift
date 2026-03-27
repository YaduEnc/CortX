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
