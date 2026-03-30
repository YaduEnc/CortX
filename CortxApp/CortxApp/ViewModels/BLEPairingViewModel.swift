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
    @Published var wifiStatusMessage = "Wi-Fi idle"
    @Published var canConfigureWifi = false
    @Published var isSendingWifiConfig = false
    @Published var isLiveStreaming = false
    @Published var liveStatusMessage = "Live gateway idle."
    @Published var liveErrorMessage: String?
    @Published var liveFramesSent = 0
    @Published var livePacketsReceived = 0
    @Published var livePacketDrops = 0

    private lazy var centralManager = CBCentralManager(delegate: self, queue: .main)
    private var peripherals: [UUID: CBPeripheral] = [:]

    private var selectedPeripheralID: UUID?
    private var connectedPeripheral: CBPeripheral?
    private var pairService: CBService?
    private var deviceInfoCharacteristic: CBCharacteristic?
    private var pairNonceCharacteristic: CBCharacteristic?
    private var pairTokenCharacteristic: CBCharacteristic?
    private var pairStatusCharacteristic: CBCharacteristic?
    private var wifiConfigCharacteristic: CBCharacteristic?
    private var wifiStatusCharacteristic: CBCharacteristic?
    private var audioControlCharacteristic: CBCharacteristic?
    private var audioDataCharacteristic: CBCharacteristic?
    private var audioStateCharacteristic: CBCharacteristic?

    private var readDeviceInfo: BLEDeviceInfo?
    private var readPairNonce: String?
    private var backendPairingRequested = false
    private var requestInFlightTask: Task<Void, Never>?
    private var statusTimeoutTask: Task<Void, Never>?
    private var shouldIgnoreDisconnectFailure = false
    private var liveStartTask: Task<Void, Never>?
    private var liveAutoConnect = false
    private var liveTargetDeviceCode: String?

    private var wsTask: URLSessionWebSocketTask?
    private var wsReady = false
    private var wsConnected = false
    private var wsSessionID: String?
    private var wsSeq = 0
    private var wsSending = false
    private var wsPendingFrames: [Data] = []
    private var pcmAccumulator = Data()
    private var frameDurationMs = 500
    private var frameBytes = 8000
    private var expectedBleSeq: UInt32?

    private var activeAppToken: String?
    private var apiClient: APIClient?

    override init() {
        super.init()
        _ = centralManager
    }

    deinit {
        requestInFlightTask?.cancel()
        statusTimeoutTask?.cancel()
        liveStartTask?.cancel()
        wsTask?.cancel(with: .goingAway, reason: nil)
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

    func disconnect() {
        if isLiveStreaming {
            stopLiveStreaming()
        }
        shouldIgnoreDisconnectFailure = true
        if let connectedPeripheral {
            centralManager.cancelPeripheralConnection(connectedPeripheral)
        }
        connectedPeripheral = nil
        canConfigureWifi = false
    }

    func sendWifiConfig(ssid: String, password: String) {
        guard let peripheral = connectedPeripheral else {
            errorMessage = "Connect to a device first."
            return
        }
        guard let wifiConfigCharacteristic else {
            errorMessage = "Device does not expose Wi-Fi config characteristic."
            return
        }

        let normalizedSSID = ssid.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedSSID.isEmpty else {
            errorMessage = "SSID is required."
            return
        }

        let payload: [String: Any] = [
            "ssid": normalizedSSID,
            "password": password,
            "persist": true
        ]
        guard
            let data = try? JSONSerialization.data(withJSONObject: payload),
            let text = String(data: data, encoding: .utf8),
            let value = text.data(using: .utf8)
        else {
            errorMessage = "Failed to encode Wi-Fi payload."
            return
        }

        isSendingWifiConfig = true
        wifiStatusMessage = "Sending Wi-Fi config..."
        errorMessage = nil
        peripheral.writeValue(value, for: wifiConfigCharacteristic, type: .withResponse)
    }

    func startLiveStreaming(deviceCode: String, appToken: String, apiClient: APIClient) {
        guard !isLiveStreaming else { return }
        guard centralManager.state == .poweredOn else {
            liveErrorMessage = "Bluetooth is not ready."
            return
        }

        liveErrorMessage = nil
        liveStatusMessage = "Starting live gateway..."
        isLiveStreaming = true
        liveFramesSent = 0
        livePacketsReceived = 0
        livePacketDrops = 0
        expectedBleSeq = nil
        pcmAccumulator.removeAll(keepingCapacity: true)
        wsPendingFrames.removeAll(keepingCapacity: true)
        wsSeq = 0
        wsReady = false
        wsConnected = false

        activeAppToken = appToken
        self.apiClient = apiClient
        liveTargetDeviceCode = deviceCode

        liveStartTask = Task {
            do {
                let startResp = try await apiClient.startAppLiveStream(
                    deviceCode: deviceCode,
                    sampleRate: 8000,
                    channels: 1,
                    codec: "pcm16le",
                    frameDurationMs: 500,
                    accessToken: appToken
                )
                await MainActor.run {
                    self.wsSessionID = startResp.session_id
                    self.frameDurationMs = startResp.frame_duration_ms
                    self.frameBytes = max(320, startResp.sample_rate * startResp.frame_duration_ms / 1000 * 2)
                    self.openWebSocket(wsPath: startResp.ws_url)
                    self.connectForLiveAudioIfNeeded()
                    self.liveStatusMessage = "Live stream prepared. Waiting for BLE audio..."
                }
            } catch {
                await MainActor.run {
                    self.isLiveStreaming = false
                    self.liveErrorMessage = "Live start failed: \(error.localizedDescription)"
                    self.liveStatusMessage = "Live gateway failed."
                }
            }
        }
    }

    func stopLiveStreaming(resetBleState: Bool = true) {
        if let peripheral = connectedPeripheral, let audioControlCharacteristic {
            if let stopData = "stop".data(using: .utf8) {
                peripheral.writeValue(stopData, for: audioControlCharacteristic, type: .withResponse)
            }
        }

        flushPendingPcmAsFrame()
        sendWebSocketControl(type: "end", reason: "app_stop")
        wsTask?.cancel(with: .goingAway, reason: nil)
        wsTask = nil
        wsConnected = false
        wsReady = false
        wsSending = false
        wsPendingFrames.removeAll(keepingCapacity: false)
        pcmAccumulator.removeAll(keepingCapacity: false)
        isLiveStreaming = false
        liveAutoConnect = false
        liveTargetDeviceCode = nil
        liveStatusMessage = "Live gateway stopped."
        if resetBleState {
            expectedBleSeq = nil
        }
    }

    private func connectForLiveAudioIfNeeded() {
        guard isLiveStreaming else { return }
        if let connectedPeripheral, audioControlCharacteristic != nil, audioDataCharacteristic != nil {
            sendLiveStartToDevice(peripheral: connectedPeripheral)
            return
        }

        liveAutoConnect = true
        startScanning()
        liveStatusMessage = "Scanning BLE device for live audio..."
    }

    private func sendLiveStartToDevice(peripheral: CBPeripheral) {
        guard let audioControlCharacteristic else { return }
        guard let startData = "start".data(using: .utf8) else { return }
        peripheral.writeValue(startData, for: audioControlCharacteristic, type: .withResponse)
        liveStatusMessage = "Start command sent to device."
    }

    private func openWebSocket(wsPath: String) {
        wsTask?.cancel(with: .goingAway, reason: nil)
        wsTask = nil

        guard let url = buildWebSocketURL(from: wsPath) else {
            liveErrorMessage = "Invalid ws URL from server."
            isLiveStreaming = false
            return
        }

        let task = URLSession.shared.webSocketTask(with: url)
        wsTask = task
        task.resume()
        wsConnected = true
        receiveWebSocketLoop()
    }

    private func buildWebSocketURL(from wsPath: String) -> URL? {
        if wsPath.hasPrefix("ws://") || wsPath.hasPrefix("wss://") {
            return URL(string: wsPath)
        }

        var root = AppConfig.apiBaseURL.absoluteString
        if root.hasPrefix("https://") {
            root = root.replacingOccurrences(of: "https://", with: "wss://")
        } else if root.hasPrefix("http://") {
            root = root.replacingOccurrences(of: "http://", with: "ws://")
        }
        if root.hasSuffix("/v1") {
            root.removeLast(3)
        }
        let full = wsPath.hasPrefix("/") ? root + wsPath : root + "/" + wsPath
        return URL(string: full)
    }

    private func receiveWebSocketLoop() {
        guard let wsTask else { return }
        wsTask.receive { [weak self] result in
            guard let self else { return }
            DispatchQueue.main.async {
                switch result {
                case let .success(message):
                    self.handleWebSocketMessage(message)
                    self.receiveWebSocketLoop()
                case let .failure(error):
                    if self.isLiveStreaming {
                        self.liveErrorMessage = "WS receive failed: \(error.localizedDescription)"
                        self.liveStatusMessage = "WebSocket disconnected."
                        self.isLiveStreaming = false
                    }
                }
            }
        }
    }

    private func handleWebSocketMessage(_ message: URLSessionWebSocketTask.Message) {
        let text: String
        switch message {
        case let .string(value):
            text = value
        case let .data(value):
            guard let valueText = String(data: value, encoding: .utf8) else { return }
            text = valueText
        @unknown default:
            return
        }

        guard
            let data = text.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let type = (json["type"] as? String)?.lowercased()
        else {
            return
        }

        switch type {
        case "ready":
            wsReady = true
            wsSeq = (json["next_seq"] as? Int) ?? wsSeq
            liveStatusMessage = "WS ready. Streaming..."
            pumpWebSocketSend()
        case "ack":
            break
        case "nack":
            liveErrorMessage = "Server requested retransmit; restarting stream is safer."
        case "finalized":
            isLiveStreaming = false
            liveStatusMessage = "Finalized on server."
        case "error":
            let message = (json["message"] as? String) ?? "Unknown websocket error"
            liveErrorMessage = message
            isLiveStreaming = false
        default:
            break
        }
    }

    private func sendWebSocketControl(type: String, reason: String) {
        guard let wsTask, wsConnected else { return }
        let payload: [String: Any] = ["type": type, "reason": reason]
        guard
            let data = try? JSONSerialization.data(withJSONObject: payload),
            let text = String(data: data, encoding: .utf8)
        else {
            return
        }
        wsTask.send(.string(text)) { _ in }
    }

    private func enqueueFrameForUpload(_ frame: Data) {
        var packet = Data(capacity: 4 + frame.count)
        let seq = UInt32(wsSeq)
        packet.append(UInt8((seq >> 24) & 0xFF))
        packet.append(UInt8((seq >> 16) & 0xFF))
        packet.append(UInt8((seq >> 8) & 0xFF))
        packet.append(UInt8(seq & 0xFF))
        packet.append(frame)

        wsPendingFrames.append(packet)
        wsSeq += 1
        pumpWebSocketSend()
    }

    private func pumpWebSocketSend() {
        guard wsReady, wsConnected, !wsSending, !wsPendingFrames.isEmpty, let wsTask else {
            return
        }
        let packet = wsPendingFrames.removeFirst()
        wsSending = true
        wsTask.send(.data(packet)) { [weak self] error in
            guard let self else { return }
            DispatchQueue.main.async {
                self.wsSending = false
                if let error {
                    self.liveErrorMessage = "WS send failed: \(error.localizedDescription)"
                    self.isLiveStreaming = false
                    return
                }
                self.liveFramesSent += 1
                self.pumpWebSocketSend()
            }
        }
    }

    private func handleAudioDataPacket(_ value: Data) {
        guard isLiveStreaming else { return }
        guard value.count > 4 else { return }

        let seq = value.prefix(4).reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
        if let expectedBleSeq, seq != expectedBleSeq {
            if seq > expectedBleSeq {
                livePacketDrops += Int(seq - expectedBleSeq)
            }
        }
        expectedBleSeq = seq + 1
        livePacketsReceived += 1

        let pcm = value.dropFirst(4)
        pcmAccumulator.append(contentsOf: pcm)
        while pcmAccumulator.count >= frameBytes {
            let frame = Data(pcmAccumulator.prefix(frameBytes))
            pcmAccumulator.removeFirst(frameBytes)
            enqueueFrameForUpload(frame)
        }
    }

    private func flushPendingPcmAsFrame() {
        guard !pcmAccumulator.isEmpty else { return }
        var padded = pcmAccumulator
        if padded.count < frameBytes {
            padded.append(contentsOf: [UInt8](repeating: 0, count: frameBytes - padded.count))
        }
        enqueueFrameForUpload(Data(padded.prefix(frameBytes)))
        pcmAccumulator.removeAll(keepingCapacity: false)
    }

    private func resetPairingState(keepDiscovery: Bool) {
        requestInFlightTask?.cancel()
        requestInFlightTask = nil
        statusTimeoutTask?.cancel()
        statusTimeoutTask = nil
        liveStartTask?.cancel()
        liveStartTask = nil

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
        wifiConfigCharacteristic = nil
        wifiStatusCharacteristic = nil
        audioControlCharacteristic = nil
        audioDataCharacteristic = nil
        audioStateCharacteristic = nil
        backendPairingRequested = false
        shouldIgnoreDisconnectFailure = false
        activeAppToken = nil
        apiClient = nil
        statusMessage = "Ready to pair."
        wifiStatusMessage = "Wi-Fi idle"
        canConfigureWifi = false
        isSendingWifiConfig = false
        stopLiveStreaming(resetBleState: false)

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
            } catch let apiError as APIClientError {
                await MainActor.run {
                    if case .unauthorized = apiError {
                        self.failPairing("Session expired. Login again, then retry pairing.")
                    } else {
                        self.failPairing(apiError.localizedDescription)
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
            try? await Task.sleep(nanoseconds: 45_000_000_000)
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

        if liveAutoConnect, connectedPeripheral == nil {
            stopScanning()
            selectedPeripheralID = peripheral.identifier
            connectedPeripheral = peripheral
            peripheral.delegate = self
            statusMessage = "Connecting BLE for live audio..."
            central.connect(peripheral, options: nil)
        }
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
        connectedPeripheral = nil
        canConfigureWifi = false
        isSendingWifiConfig = false
        if isLiveStreaming {
            liveErrorMessage = error?.localizedDescription ?? "BLE disconnected during live stream."
            stopLiveStreaming()
        }
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
            CBUUID(string: AppConfig.BLE.pairStatusCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.wifiConfigCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.wifiStatusCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.audioControlCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.audioDataCharacteristicUUID),
            CBUUID(string: AppConfig.BLE.audioStateCharacteristicUUID)
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
            case AppConfig.BLE.wifiConfigCharacteristicUUID:
                wifiConfigCharacteristic = characteristic
            case AppConfig.BLE.wifiStatusCharacteristicUUID:
                wifiStatusCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
                peripheral.readValue(for: characteristic)
            case AppConfig.BLE.audioControlCharacteristicUUID:
                audioControlCharacteristic = characteristic
            case AppConfig.BLE.audioDataCharacteristicUUID:
                audioDataCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
            case AppConfig.BLE.audioStateCharacteristicUUID:
                audioStateCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
                peripheral.readValue(for: characteristic)
            default:
                break
            }
        }
        canConfigureWifi = (wifiConfigCharacteristic != nil && wifiStatusCharacteristic != nil)
        if liveAutoConnect, isLiveStreaming, audioControlCharacteristic != nil, audioDataCharacteristic != nil {
            liveAutoConnect = false
            sendLiveStartToDevice(peripheral: peripheral)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error {
            failPairing(error.localizedDescription)
            return
        }
        guard let value = characteristic.value else {
            return
        }
        let uuid = characteristic.uuid.uuidString.lowercased()
        if uuid == AppConfig.BLE.audioDataCharacteristicUUID {
            handleAudioDataPacket(value)
            return
        }
        guard let text = String(data: value, encoding: .utf8) else {
            return
        }

        switch uuid {
        case AppConfig.BLE.deviceInfoCharacteristicUUID:
            let info = parseDeviceInfo(text)
            readDeviceInfo = info
            discoveredDeviceCode = info.deviceCode
        case AppConfig.BLE.pairNonceCharacteristicUUID:
            readPairNonce = text.trimmingCharacters(in: .whitespacesAndNewlines)
        case AppConfig.BLE.pairStatusCharacteristicUUID:
            handlePairStatusUpdate(text.trimmingCharacters(in: .whitespacesAndNewlines))
        case AppConfig.BLE.wifiStatusCharacteristicUUID:
            wifiStatusMessage = text.trimmingCharacters(in: .whitespacesAndNewlines)
            isSendingWifiConfig = false
        case AppConfig.BLE.audioStateCharacteristicUUID:
            liveStatusMessage = text.trimmingCharacters(in: .whitespacesAndNewlines)
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
        } else if characteristic.uuid.uuidString.lowercased() == AppConfig.BLE.wifiConfigCharacteristicUUID {
            wifiStatusMessage = "Wi-Fi config sent. Waiting for device status..."
            isSendingWifiConfig = false
        } else if characteristic.uuid.uuidString.lowercased() == AppConfig.BLE.audioControlCharacteristicUUID {
            liveStatusMessage = "Live control sent to device."
        }
    }
}
