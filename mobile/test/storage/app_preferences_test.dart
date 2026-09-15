import 'package:flutter_test/flutter_test.dart';
import 'package:plane_assistant/storage/app_preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('setWidgetToken persists a readable plaintext mirror', () async {
    final prefs = await AppPreferences.create();
    await prefs.setWidgetToken('abc123');

    // Read back through the raw SharedPreferences instance the way the
    // native VoiceRecordingService does (a different key namespace than
    // any AppPreferences getter), to prove the value actually lands where
    // that Kotlin code expects it.
    final raw = await SharedPreferences.getInstance();
    expect(raw.getString('widget_gateway_api_token'), 'abc123');
  });

  test('setWidgetToken(null) removes the mirror', () async {
    final prefs = await AppPreferences.create();
    await prefs.setWidgetToken('abc123');
    await prefs.setWidgetToken(null);

    final raw = await SharedPreferences.getInstance();
    expect(raw.getString('widget_gateway_api_token'), isNull);
  });

  test('clearServerConfig also clears the widget token mirror', () async {
    final prefs = await AppPreferences.create();
    await prefs.setServerUrl('http://example.com');
    await prefs.setWidgetToken('abc123');

    await prefs.clearServerConfig();

    final raw = await SharedPreferences.getInstance();
    expect(raw.getString('widget_gateway_api_token'), isNull);
    expect(prefs.serverUrl, isNull);
  });
}
