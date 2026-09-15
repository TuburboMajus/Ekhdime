// Smoke test: verifies the app boots to the server-setup screen when no
// server URL has been configured yet, without crashing.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:plane_assistant/main.dart';
import 'package:plane_assistant/storage/app_preferences.dart';
import 'package:plane_assistant/storage/secure_storage.dart';

import 'helpers/fake_secure_storage.dart';

void main() {
  testWidgets('App shows server setup screen on first launch', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await AppPreferences.create();
    final secureStorage = SecureStorage(storage: FakeFlutterSecureStorage());

    await tester.pumpWidget(PlaneAssistantApp(
      preferences: preferences,
      secureStorage: secureStorage,
    ));
    await tester.pumpAndSettle();

    expect(find.text('Connect to your Plane gateway'), findsOneWidget);
    expect(find.byKey(const Key('server_url_field')), findsOneWidget);
    expect(find.byKey(const Key('api_token_field')), findsOneWidget);
  });
}
