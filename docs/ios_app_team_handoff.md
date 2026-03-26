# iOS App Team Handoff

This app implementation is in:
- `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp`

## Implemented flow
1. User register/login against production API:
   - `POST /v1/app/register`
   - `POST /v1/app/auth`
2. JWT stored in Keychain.
3. Auth-gated app:
   - logged-out users see Auth screen only
   - logged-in users see Dashboard only
4. Paired devices list:
   - `GET /v1/app/devices`
5. Capture browser + playback:
   - `GET /v1/app/captures`
   - `GET /v1/app/captures/{session_id}/audio`
   - `GET /v1/app/captures/{session_id}/transcript`
5. BLE pairing flow:
   - scan by pairing service UUID
   - read `device_info` + `pair_nonce`
   - call `POST /v1/pairing/start`
   - write returned `pair_token` to BLE `pair_token` characteristic
   - listen to BLE `pair_status` notifications
   - on `success`, refresh paired devices list

## Production API base URL in app
- `https://hamza.yaduraj.me/v1`

Defined in:
- `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/AppConfig.swift`

## BLE UUIDs used
- service: `8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0`
- `device_info`: `94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1`
- `pair_nonce`: `2dc45f2c-5924-48cf-a615-f9e3c1070ad4`
- `pair_token`: `9f8b48ad-e983-4abf-8b56-53f31c0f7596`
- `pair_status`: `ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d`

## iOS code map
- API: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/Services/APIClient.swift`
- Keychain token: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/Services/KeychainTokenStore.swift`
- App session/auth state: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/ViewModels/AppSessionViewModel.swift`
- BLE pairing engine: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/ViewModels/BLEPairingViewModel.swift`
- Audio playback manager: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/Services/AudioPlaybackManager.swift`
- Auth UI: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/Views/AuthView.swift`
- Dashboard + Pair sheet UI: `/Users/sujeetkumarsingh/Desktop/CortX/CortxApp/CortxApp/Views/DashboardView.swift`

## Build check already run
Command used:
`xcodebuild -project CortxApp/CortxApp.xcodeproj -scheme CortxApp -configuration Debug -destination 'generic/platform=iOS' -derivedDataPath /tmp/CortxDerived CODE_SIGNING_ALLOWED=NO build`

Result:
- `BUILD SUCCEEDED`
