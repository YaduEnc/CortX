import CoreBluetooth
import Foundation
import Combine

struct DiscoveredBLEDevice: Identifiable, Equatable {
    let id: UUID
    let name: String
    let rssi: Int
}

final class BLEPairingViewModel: NSObject, ObservableObject {
    @Published var bluetoothReady = false
    @Published var isScanning = false
    @Published var isBusy = false
    @Published var devices: [DiscoveredBLEDevice] = []
    @Published var statusMessage = "Bluetooth is initializing..."
    @Published var errorMessage: String?
    @Published var pairingStatus: PairingStatus = .idle
    @Published var discoveredDeviceCode: String?

    private lazy var centralManager = CBCentralManager(delegate: self, queue: .main)
    private var peripherals: [UUID: CBPeripheral] = [:]

    private var selectedPeripheralID: UUID?
    private var connectedPeripheral: CBPeripheral?
    private var pairService: CBService?
    private var deviceInfoCharacteristic: CBCharacteristic?
    private var pairNonceCharacteristic: CBCharacteristic?
    private var pairTokenCharacteristic: CBCharacteristic?
    private var pairStatusCharacteristic: CBCharacteristic?

    private var readDeviceInfo: BLEDeviceInfo?
    private var readPairNonce: String?
    private var backendPairingRequested = false
    private var requestInFlightTask: Task<Void, Never>?
    private var statusTimeoutTask: Task<Void, Never>?
    private var shouldIgnoreDisconnectFailure = false

    private var activeAppToken: String?
    private var apiClient: APIClient?

    override init() {
        super.init()
        _ = centralManager
    }

    deinit {
        requestInFlightTask?.cancel()
        statusTimeoutTask?.cancel()
    }

    func startScanning() {
        guard centralManager.state == .poweredOn else {
            switch centralManager.state {
            case .poweredOff:
                errorMessage = "Bluetooth is not powered on."
                statusMessage = "Turn on Bluetooth and retry."
            case .unauthorized:
                errorMessage = "Bluetooth permission denied. Allow Bluetooth access in Settings."
                statusMessage = "Bluetooth permission required."
            case .unsupported:
                errorMessage = "Bluetooth is not supported on this device."
                statusMessage = "Bluetooth unsupported."
            default:
                errorMessage = "Bluetooth is initializing. Wait 2 seconds and tap Scan again."
                statusMessage = "Bluetooth is initializing..."
            }
            return
        }

        stopScanning()
        devices = []
        peripherals = [:]
        errorMessage = nil
        statusMessage = "Scanning for SecondMind devices..."

        // Use broad scan and manually filter, because some ESP32 builds advertise
        // custom 128-bit service UUIDs in a way iOS service-filter scan may miss.
        centralManager.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
        isScanning = true
    }

    func stopScanning() {
        if isScanning {
            centralManager.stopScan()
        }
        isScanning = false
    }

    func pair(with device: DiscoveredBLEDevice, appToken: String, apiClient: APIClient) {
        guard centralManager.state == .poweredOn else {
            errorMessage = "Bluetooth is not available."
            return
        }
        guard let peripheral = peripherals[device.id] else {
            errorMessage = "Device not found. Scan again."
            return
        }

        resetPairingState(keepDiscovery: true)
        activeAppToken = appToken
        self.apiClient = apiClient
        selectedPeripheralID = device.id
        connectedPeripheral = peripheral

        isBusy = true
        statusMessage = "Connecting to \(device.name)..."
        pairingStatus = .pending
        errorMessage = nil

        peripheral.delegate = self
        centralManager.connect(peripheral, options: nil)
    }

    func clearTransientErrors() {
        errorMessage = nil
    }

    private func resetPairingState(keepDiscovery: Bool) {
        requestInFlightTask?.cancel()
        requestInFlightTask = nil
        statusTimeoutTask?.cancel()
        statusTimeoutTask = nil

        isBusy = false
        pairingStatus = .idle
        readDeviceInfo = nil
        readPairNonce = nil
        discoveredDeviceCode = nil
        selectedPeripheralID = nil
        connectedPeripheral = nil
        pairService = nil
        deviceInfoCharacteristic = nil
        pairNonceCharacteristic = nil
        pairTokenCharacteristic = nil
        pairStatusCharacteristic = nil
        backendPairingRequested = false
        shouldIgnoreDisconnectFailure = false
        activeAppToken = nil
        apiClient = nil
        statusMessage = "Ready to pair."

        if !keepDiscovery {
            devices = []
            peripherals = [:]
        }
    }

    private func startBackendPairingIfReady() {
        guard !backendPairingRequested else { return }
        guard
            let token = activeAppToken,
            let apiClient,
            let deviceCode = readDeviceInfo?.deviceCode.trimmingCharacters(in: .whitespacesAndNewlines),
            let pairNonce = readPairNonce?.trimmingCharacters(in: .whitespacesAndNewlines),
            let pairTokenCharacteristic,
            let peripheral = connectedPeripheral
        else {
            return
        }
        guard !deviceCode.isEmpty, !pairNonce.isEmpty else { return }

        backendPairingRequested = true
        statusMessage = "Requesting pair token..."

        requestInFlightTask = Task {
            do {
                let response = try await apiClient.startPairing(
                    deviceCode: deviceCode,
                    pairNonce: pairNonce,
                    accessToken: token
                )
                await MainActor.run {
                    self.statusMessage = "Sending token to device..."
                    self.discoveredDeviceCode = deviceCode
                    if let data = response.pair_token.data(using: .utf8) {
                        peripheral.writeValue(data, for: pairTokenCharacteristic, type: .withResponse)
                        self.startStatusTimeout()
                    } else {
                        self.failPairing("Failed to encode pairing token.")
                    }
                }
            } catch {
                await MainActor.run {
                    self.failPairing(error.localizedDescription)
                }
            }
        }
    }

    private func startStatusTimeout() {
        statusTimeoutTask?.cancel()
        statusTimeoutTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 25_000_000_000)
            await MainActor.run {
                guard let self, self.isBusy else { return }
                self.failPairing("Pairing timed out. Retry pairing mode on the device.")
            }
        }
    }

    private func failPairing(_ message: String) {
        statusTimeoutTask?.cancel()
        requestInFlightTask?.cancel()
        isBusy = false
        pairingStatus = .failed
        errorMessage = message
        statusMessage = "Pairing failed"

        shouldIgnoreDisconnectFailure = true
        if let connectedPeripheral {
            centralManager.cancelPeripheralConnection(connectedPeripheral)
        }
    }

    private func handlePairStatusUpdate(_ rawStatus: String) {
        let status = PairingStatus(rawValueOrUnknown: rawStatus)
        pairingStatus = status
        statusMessage = status.userLabel

        switch status {
        case .success:
            statusTimeoutTask?.cancel()
            isBusy = false
            errorMessage = nil
            shouldIgnoreDisconnectFailure = true
            if let connectedPeripheral {
                centralManager.cancelPeripheralConnection(connectedPeripheral)
            }
        case .failed, .expired:
            failPairing(status.userLabel)
        default:
            break
        }
    }

    private func parseDeviceInfo(_ raw: String) -> BLEDeviceInfo {
        if
            let data = raw.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        {
            let deviceCode = (json["device_code"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let firmwareVersion = json["fw_version"] as? String
            return BLEDeviceInfo(deviceCode: deviceCode, firmwareVersion: firmwareVersion, rawPayload: raw)
        }

        return BLEDeviceInfo(
            deviceCode: raw.trimmingCharacters(in: .whitespacesAndNewlines),
            firmwareVersion: nil,
            rawPayload: raw
        )
    }
}

extension BLEPairingViewModel: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        bluetoothReady = (central.state == .poweredOn)
        switch central.state {
        case .poweredOn:
            statusMessage = "Bluetooth is ready."
            errorMessage = nil
        case .poweredOff:
            statusMessage = "Bluetooth is off."
            stopScanning()
        case .unauthorized:
            statusMessage = "Bluetooth permission denied."
            errorMessage = "Enable Bluetooth permission in iOS Settings."
            stopScanning()
        case .unsupported:
            statusMessage = "Bluetooth unsupported on this device."
            stopScanning()
        default:
            statusMessage = "Bluetooth unavailable."
            stopScanning()
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let advertisedName = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String)
        let nameForMatch = advertisedName?.lowercased() ?? ""

        let advertisedServices = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID]) ?? []
        let overflowServices = (advertisementData[CBAdvertisementDataOverflowServiceUUIDsKey] as? [CBUUID]) ?? []
        let allServices = advertisedServices + overflowServices
        let hasPairService = allServices.contains { $0.uuidString.caseInsensitiveCompare(AppConfig.BLE.pairServiceUUID) == .orderedSame }

        let looksLikeSecondMindName =
            nameForMatch.contains("secondmind") ||
            nameForMatch.contains("esp32") ||
            nameForMatch.contains("xiao")
        guard hasPairService || looksLikeSecondMindName else {
            return
        }

        let displayName = advertisedName ?? (hasPairService ? "SecondMind Device" : "Unknown BLE Device")
        peripherals[peripheral.identifier] = peripheral

        if let index = devices.firstIndex(where: { $0.id == peripheral.identifier }) {
            devices[index] = DiscoveredBLEDevice(id: peripheral.identifier, name: displayName, rssi: RSSI.intValue)
        } else {
            devices.append(DiscoveredBLEDevice(id: peripheral.identifier, name: displayName, rssi: RSSI.intValue))
        }

        devices.sort { $0.rssi > $1.rssi }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        statusMessage = "Connected. Reading pairing data..."
        peripheral.delegate = self
        peripheral.discoverServices([CBUUID(string: AppConfig.BLE.pairServiceUUID)])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        isBusy = false
        errorMessage = error?.localizedDescription ?? "Failed to connect to device."
        statusMessage = "Connection failed."
        pairingStatus = .failed
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        if isBusy && !shouldIgnoreDisconnectFailure {
            failPairing(error?.localizedDescription ?? "Device disconnected during pairing.")
        } else {
            isBusy = false
        }
    }
}

extension BLEPairingViewModel: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error {
            failPairing(error.localizedDescription)
            return
        }

        guard
            let service = peripheral.services?.first(where: { $0.uuid.uuidString.lowercased() == AppConfig.BLE.pairServiceUUID })
        else {
            failPairing("Pairing service not found.")
            return
        }

        pairService = service
        let uuids = [
            CBUUID(string: AppConfig.BLE.deviceInfoCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.pairNonceCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.pairTokenCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.pairStatusCharacteristicUUID)
        ]
        peripheral.discoverCharacteristics(uuids, for: service)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error {
            failPairing(error.localizedDescription)
            return
        }

        guard let characteristics = service.characteristics else {
            failPairing("No characteristics found.")
            return
        }

        for characteristic in characteristics {
            let uuid = characteristic.uuid.uuidString.lowercased()
            switch uuid {
            case AppConfig.BLE.deviceInfoCharacteristicUUID:
                deviceInfoCharacteristic = characteristic
                peripheral.readValue(for: characteristic)
            case AppConfig.BLE.pairNonceCharacteristicUUID:
                pairNonceCharacteristic = characteristic
                peripheral.readValue(for: characteristic)
            case AppConfig.BLE.pairTokenCharacteristicUUID:
                pairTokenCharacteristic = characteristic
            case AppConfig.BLE.pairStatusCharacteristicUUID:
                pairStatusCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
                peripheral.readValue(for: characteristic)
            default:
                break
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error {
            failPairing(error.localizedDescription)
            return
        }
        guard let value = characteristic.value, let text = String(data: value, encoding: .utf8) else {
            return
        }

        let uuid = characteristic.uuid.uuidString.lowercased()
        switch uuid {
        case AppConfig.BLE.deviceInfoCharacteristicUUID:
            let info = parseDeviceInfo(text)
            readDeviceInfo = info
            discoveredDeviceCode = info.deviceCode
        case AppConfig.BLE.pairNonceCharacteristicUUID:
            readPairNonce = text.trimmingCharacters(in: .whitespacesAndNewlines)
        case AppConfig.BLE.pairStatusCharacteristicUUID:
            handlePairStatusUpdate(text.trimmingCharacters(in: .whitespacesAndNewlines))
        default:
            break
        }

        startBackendPairingIfReady()
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error {
            failPairing(error.localizedDescription)
            return
        }

        if characteristic.uuid.uuidString.lowercased() == AppConfig.BLE.pairTokenCharacteristicUUID {
            statusMessage = "Pair token sent. Waiting for device confirmation..."
        }
    }
}
