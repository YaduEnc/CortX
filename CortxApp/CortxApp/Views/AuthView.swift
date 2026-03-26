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

    var body: some View {
        ZStack {
            AppBackgroundView()

            VStack(spacing: 18) {
                VStack(spacing: 6) {
                    Text("SecondMind")
                        .font(.system(size: 34, weight: .bold, design: .rounded))
                        .foregroundStyle(Color.primary)
                    Text("Cognitive OS for your thinking")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 24)

                Picker("Auth Mode", selection: $mode) {
                    ForEach(Mode.allCases, id: \.self) { current in
                        Text(current.rawValue).tag(current)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 18)
                .onChange(of: mode) { _, _ in
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.9)) {
                        session.errorMessage = nil
                    }
                }

                VStack(spacing: 12) {
                    if mode == .signup {
                        TextField("Full name (optional)", text: $fullName)
                            .textContentType(.name)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .transition(.move(edge: .top).combined(with: .opacity))
                    }

                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textFieldStyle(RoundedBorderTextFieldStyle())

                    Group {
                        if showPassword {
                            TextField("Password", text: $password)
                                .textContentType(.password)
                        } else {
                            SecureField("Password", text: $password)
                                .textContentType(.password)
                        }
                    }
                    .textFieldStyle(RoundedBorderTextFieldStyle())

                    Toggle("Show password", isOn: $showPassword)
                        .font(.footnote)
                        .tint(.blue)
                }
                .padding(18)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(.ultraThinMaterial)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.white.opacity(0.45), lineWidth: 1)
                )
                .padding(.horizontal, 18)

                if let error = session.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .padding(.horizontal, 22)
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
                    HStack {
                        if session.isWorking {
                            ProgressView()
                                .tint(.white)
                        }
                        Text(mode == .login ? "Login" : "Create Account")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .disabled(session.isWorking)
                .padding(.horizontal, 18)
                .padding(.bottom, 24)
            }
        }
    }
}
