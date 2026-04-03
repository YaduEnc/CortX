import SwiftUI

struct ProfileSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var session: AppSessionViewModel

    @State private var fullName: String = ""
    @State private var timezone: String = TimeZone.current.identifier
    @State private var dailySummaryEnabled = true
    @State private var reminderNotificationsEnabled = true
    @State private var calendarExportDefaultEnabled = false
    @State private var message: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Account") {
                    TextField("Full Name", text: $fullName)
                    HStack {
                        Text("Email")
                        Spacer()
                        Text(session.userEmail)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Preferences") {
                    TextField("Timezone", text: $timezone)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Toggle("Daily summary enabled", isOn: $dailySummaryEnabled)
                    Toggle("Reminder notifications", isOn: $reminderNotificationsEnabled)
                    Toggle("Default calendar export", isOn: $calendarExportDefaultEnabled)
                }

                Section {
                    Button("Save Profile") {
                        Task { await saveProfile() }
                    }
                    .buttonStyle(LiquidPrimaryButtonStyle())
                    .disabled(session.isWorking)

                    if let message {
                        Text(message)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(AppBackgroundView())
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") {
                        dismiss()
                    }
                }
            }
            .onAppear {
                fullName = session.userFullName ?? ""
                if let prefs = session.userPreferences {
                    timezone = prefs.timezone
                    dailySummaryEnabled = prefs.daily_summary_enabled
                    reminderNotificationsEnabled = prefs.reminder_notifications_enabled
                    calendarExportDefaultEnabled = prefs.calendar_export_default_enabled
                }
            }
        }
    }

    private func saveProfile() async {
        let nameOK = await session.updateCurrentUser(fullName: fullName)
        let prefsOK = await session.updateUserPreferences(
            timezone: timezone,
            dailySummaryEnabled: dailySummaryEnabled,
            reminderNotificationsEnabled: reminderNotificationsEnabled,
            calendarExportDefaultEnabled: calendarExportDefaultEnabled
        )

        if nameOK && prefsOK {
            await session.refreshDailySummary(showLoader: false)
            message = "Profile updated."
        } else {
            message = session.errorMessage ?? "Failed to update profile."
        }
    }
}
