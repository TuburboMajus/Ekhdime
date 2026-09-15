# Plane Assistant -- Mobile (Android)

A minimal Flutter client for the gateway component in `../gateway/`. This is
the *only* thing the mobile app talks to -- never Plane, the MCP server,
Whisper, Kokoro, or DeepSeek directly. See `../gateway/API.md` for the full
API contract this app implements against.

Android is the primary (only) target for this MVP, per the root README's
"Non-Goals" section.

## Features

- First-launch server setup screen (URL + API token, with a live connection
  test) -- `lib/screens/server_setup_screen.dart`
- Text and voice queries against the gateway, with Markdown-rendered
  assistant replies, copy/speak/retry actions -- `lib/screens/conversation_screen.dart`
- Voice recording with a record/preview/send flow and mic-permission
  handling -- `lib/services/audio_recorder_service.dart`, `lib/widgets/recording_sheet.dart`
- Text-to-speech playback of any assistant message, plus an "auto-play
  responses" setting -- `lib/services/audio_player_service.dart`
- Settings: server URL/token, auto-play, TTS voice (fetched from the
  gateway) and speed, preferred input language, "review transcript before
  sending", connection test, about/version -- `lib/screens/settings_screen.dart`
- API token stored in `flutter_secure_storage` only, never in
  SharedPreferences, source, or logs -- `lib/storage/secure_storage.dart`

## Project layout

```text
lib/
├── main.dart
├── api/         ApiClient (every gateway endpoint), exceptions, error-code
│                to-message mapping, connection test, URL validation
├── models/      Conversation, Message, AgentInfo, AudioRef, HealthDetails, ...
├── screens/     server_setup, conversation, settings
├── services/    audio recording (record) / playback (just_audio)
├── storage/     secure_storage (token), app_preferences (everything else)
└── widgets/     message bubble, recording bottom sheet, voice picker
```

## Setup

Requires the Flutter SDK (this project was built against Flutter 3.32.7 /
Dart 3.8.1 -- check with `flutter --version`).

```bash
cd mobile
flutter pub get
```

## Running against a gateway

```bash
flutter run
```

On first launch you'll land on the server-setup screen. The URL you enter
depends on where the gateway is reachable from:

| Running the app on... | Gateway URL to enter |
| --- | --- |
| Android emulator, gateway on your host machine | `http://10.0.2.2:8088` (the emulator's alias for the host) |
| Physical device, gateway on your LAN | `http://<your-machine-LAN-IP>:8088` |
| Anything, gateway deployed remotely | `https://assistant.example.com` |

`10.0.2.2` is an emulator-only convention -- it does **not** work from a
physical device, which needs your machine's real LAN address instead.

### Cleartext (plain HTTP) traffic

Android blocks cleartext (`http://`) network traffic by default on API 28+.
For local development (`http://10.0.2.2:8088`, `http://192.168.x.x:8088`),
`android/app/src/main/AndroidManifest.xml` / a network security config
needs to allow cleartext for those specific dev hosts. **Do not** globally
disable Android's network security for release builds -- scope any
cleartext allowance to development use and use `https://` for anything
beyond your own LAN (see the root README's TLS section for a reverse-proxy
setup that gets you `https://` cheaply even for local/self-hosted use).

### Microphone permission

The app requests `RECORD_AUDIO` (via `permission_handler`) the first time
you tap the microphone button. If denied, the app explains why it's needed
and offers a button straight to the app's system settings page rather than
silently failing.

## Tests

```bash
flutter test
```

Covers: the API client against mocked HTTP responses (every endpoint, the
error-envelope-to-exception mapping, base-URL normalization), and widget
tests for the server-setup flow. `flutter analyze` should report no issues.

## Building a release APK

### Plain Flutter

```bash
flutter build apk --release
# output: build/app/outputs/flutter-apk/app-release.apk
```

### Reproducible Docker build

Every component in this repository is dockerized, including this one, even
though the app itself doesn't run as a server -- this just makes the build
reproducible/CI-friendly instead of depending on whatever Flutter/Android
SDK happens to be on a given machine.

```bash
cd mobile
cp .env.example .env   # optional: set DEFAULT_SERVER_URL to prefill the setup screen
docker compose run --rm mobile-build
# output: ./build-output/app-release.apk
```

(Note: `docker compose run --rm`, not `up -d` -- this is a one-shot build
job that exits when done, not a long-running service.)

**Memory note (found by actually running this build against a live
stack):** `flutter build apk --release` runs a memory-hungry Gradle/Android
build inside the container. If the rest of this repo's stack (`make up`) is
running at the same time on a memory-constrained machine, the Gradle daemon
can get OOM-killed (`ResourceExhausted: cannot allocate memory` / "Gradle
build daemon disappeared unexpectedly"). If `make mobile-apk` fails that way,
free up memory first -- the simplest fix is to pause the rest of the stack
for the duration of the build and resume it afterward:

```bash
docker compose -p plane-assistant stop   # from the repo root
make mobile-apk
docker compose -p plane-assistant start
```

## Non-goals for this MVP

No iOS build, no desktop build, no offline mode -- see the root README's
"Non-Goals for MVP" section. The architecture (a thin client over one REST
API) does not prevent adding any of these later.
