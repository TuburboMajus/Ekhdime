# Reproducible Android APK build.
#
# This does NOT run the app (Flutter apps need a device/emulator for that --
# see README.md for `flutter run`); it only produces a release APK the same
# way in CI as on any developer's machine. Pinned to the exact Flutter
# version this project was developed against (`flutter --version` ==
# 3.32.7), confirmed to exist via `docker manifest inspect
# ghcr.io/cirruslabs/flutter:3.32.7`.
ARG FLUTTER_VERSION=3.32.7
FROM ghcr.io/cirruslabs/flutter:${FLUTTER_VERSION}

WORKDIR /app

# Dependencies first for better layer caching.
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .

# DEFAULT_SERVER_URL is optional convenience only -- the in-app server-setup
# screen (lib/screens/server_setup_screen.dart) always works standalone
# without it; see lib/api/server_url.dart.
ARG DEFAULT_SERVER_URL=""
RUN flutter build apk --release \
    ${DEFAULT_SERVER_URL:+--dart-define=DEFAULT_SERVER_URL=${DEFAULT_SERVER_URL}}

# The compose service copies this out via a bind mount; see docker-compose.yml.
CMD ["sh", "-c", "mkdir -p /output && cp build/app/outputs/flutter-apk/app-release.apk /output/"]
