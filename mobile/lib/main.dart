import 'package:flutter/material.dart';

import 'screens/conversation_screen.dart';
import 'screens/server_setup_screen.dart';
import 'storage/app_preferences.dart';
import 'storage/secure_storage.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final preferences = await AppPreferences.create();
  final secureStorage = SecureStorage();
  runApp(PlaneAssistantApp(
    preferences: preferences,
    secureStorage: secureStorage,
  ));
}

class PlaneAssistantApp extends StatelessWidget {
  final AppPreferences preferences;
  final SecureStorage secureStorage;

  const PlaneAssistantApp({
    super.key,
    required this.preferences,
    required this.secureStorage,
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Plane Assistant',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: _StartupRouter(preferences: preferences, secureStorage: secureStorage),
    );
  }
}

/// Decides whether to show the server-setup flow or jump straight to the
/// conversation screen, based on whether a server URL has already been
/// configured. A missing/invalid token is handled later by the
/// conversation screen's own auth-error routing, since the token isn't
/// validated here (validating it requires a network round trip and we
/// don't want to block startup on that).
class _StartupRouter extends StatelessWidget {
  final AppPreferences preferences;
  final SecureStorage secureStorage;

  const _StartupRouter({required this.preferences, required this.secureStorage});

  @override
  Widget build(BuildContext context) {
    final hasServerUrl = preferences.serverUrl != null &&
        preferences.serverUrl!.isNotEmpty;
    if (hasServerUrl) {
      return ConversationScreen(
        preferences: preferences,
        secureStorage: secureStorage,
      );
    }
    return ServerSetupScreen(
      preferences: preferences,
      secureStorage: secureStorage,
    );
  }
}
