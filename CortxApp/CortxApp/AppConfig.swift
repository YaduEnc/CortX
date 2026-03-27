import Foundation

enum AppConfig {
    static let apiBaseURL = URL(string: "https://hamza.yaduraj.me/v1")!

    enum BLE {
        static let pairServiceUUID = "8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0"
        static let deviceInfoCharacteristicUUID = "94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1"
        static let pairNonceCharacteristicUUID = "2dc45f2c-5924-48cf-a615-f9e3c1070ad4"
        static let pairTokenCharacteristicUUID = "9f8b48ad-e983-4abf-8b56-53f31c0f7596"
        static let pairStatusCharacteristicUUID = "ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d"
        static let wifiConfigCharacteristicUUID = "f9eb1c79-9c16-4bc3-bd03-563a72fce6c0"
        static let wifiStatusCharacteristicUUID = "ac29d4a8-6d7f-4b91-9d9e-66e2b0fd5e61"
    }
}
