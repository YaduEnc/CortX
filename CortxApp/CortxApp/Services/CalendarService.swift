import Foundation
import EventKit

enum CalendarServiceError: LocalizedError {
    case accessDenied

    var errorDescription: String? {
        switch self {
        case .accessDenied:
            return "Calendar access denied. Enable Calendar permission in Settings."
        }
    }
}

@MainActor
final class CalendarService {
    private let store = EKEventStore()

    func addReminderToCalendar(title: String, details: String?, dueAt: Date) async throws {
        let granted = try await requestAccessIfNeeded()
        guard granted else {
            throw CalendarServiceError.accessDenied
        }

        let event = EKEvent(eventStore: store)
        event.title = title
        event.notes = details
        event.startDate = dueAt
        event.endDate = dueAt.addingTimeInterval(30 * 60)
        event.calendar = store.defaultCalendarForNewEvents
        try store.save(event, span: .thisEvent)
    }

    private func requestAccessIfNeeded() async throws -> Bool {
        if #available(iOS 17.0, *) {
            return try await store.requestFullAccessToEvents()
        }

        return try await withCheckedThrowingContinuation { continuation in
            store.requestAccess(to: .event) { granted, error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume(returning: granted)
                }
            }
        }
    }
}
