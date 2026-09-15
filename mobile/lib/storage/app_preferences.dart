import 'package:shared_preferences/shared_preferences.dart';

/// Non-secret, user-configurable settings persisted via SharedPreferences.
/// The API token lives in [SecureStorage] instead -- never here.
class AppPreferences {
  static const _serverUrlKey = 'server_url';
  static const _autoPlayKey = 'auto_play_responses';
  static const _voiceKey = 'tts_voice';
  static const _speedKey = 'tts_speed';
  static const _languageKey = 'input_language';
  static const _showTranscriptKey = 'show_transcript_before_processing';
  static const _lastConversationIdKey = 'last_conversation_id';
  // Must match VoiceRecordingService.WIDGET_TOKEN_PREF_KEY on the Android
  // side (minus the "flutter." prefix the shared_preferences plugin adds
  // to every key). See SecureStorage's docstring for why this mirror
  // exists.
  static const _widgetTokenKey = 'widget_gateway_api_token';

  final SharedPreferences _prefs;

  AppPreferences(this._prefs);

  static Future<AppPreferences> create() async {
    final prefs = await SharedPreferences.getInstance();
    return AppPreferences(prefs);
  }

  String? get serverUrl => _prefs.getString(_serverUrlKey);
  Future<void> setServerUrl(String value) =>
      _prefs.setString(_serverUrlKey, value);

  bool get autoPlayResponses => _prefs.getBool(_autoPlayKey) ?? false;
  Future<void> setAutoPlayResponses(bool value) =>
      _prefs.setBool(_autoPlayKey, value);

  String? get ttsVoice => _prefs.getString(_voiceKey);
  Future<void> setTtsVoice(String? value) => value == null
      ? _prefs.remove(_voiceKey)
      : _prefs.setString(_voiceKey, value);

  double get ttsSpeed => _prefs.getDouble(_speedKey) ?? 1.0;
  Future<void> setTtsSpeed(double value) =>
      _prefs.setDouble(_speedKey, value);

  /// ISO-639-1 code, or null for auto-detect.
  String? get inputLanguage => _prefs.getString(_languageKey);
  Future<void> setInputLanguage(String? value) => value == null
      ? _prefs.remove(_languageKey)
      : _prefs.setString(_languageKey, value);

  bool get showTranscriptBeforeProcessing =>
      _prefs.getBool(_showTranscriptKey) ?? false;
  Future<void> setShowTranscriptBeforeProcessing(bool value) =>
      _prefs.setBool(_showTranscriptKey, value);

  String? get lastConversationId => _prefs.getString(_lastConversationIdKey);
  Future<void> setLastConversationId(String? value) => value == null
      ? _prefs.remove(_lastConversationIdKey)
      : _prefs.setString(_lastConversationIdKey, value);

  Future<void> clearServerConfig() async {
    await _prefs.remove(_serverUrlKey);
    await _prefs.remove(_lastConversationIdKey);
    await _prefs.remove(_widgetTokenKey);
  }

  /// Plaintext mirror of the gateway API token, readable by the native
  /// VoiceRecordingService (which has no Flutter engine to ask, so it
  /// cannot reach [SecureStorage]'s encrypted store). Every call to
  /// `secureStorage.writeToken` must be paired with a call to this so the
  /// widget keeps working after the user updates their token.
  Future<void> setWidgetToken(String? value) => value == null || value.isEmpty
      ? _prefs.remove(_widgetTokenKey)
      : _prefs.setString(_widgetTokenKey, value);
}
