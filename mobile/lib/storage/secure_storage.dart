import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Thin wrapper around [FlutterSecureStorage] scoped to the one secret this
/// app holds: the gateway API bearer token.
///
/// The home-screen widget's recording service is native Kotlin code with no
/// running Flutter engine to ask, so it cannot read this encrypted store --
/// see [AppPreferences.setWidgetToken] for the one deliberate exception to
/// "never store the token anywhere else": a second, plaintext copy mirrored
/// into SharedPreferences (still private to this app's sandbox, just not
/// Keystore-encrypted) purely so that service can authenticate. Every
/// caller of [writeToken] must also call `setWidgetToken` with the same
/// value to keep the two in sync.
class SecureStorage {
  static const _tokenKey = 'gateway_api_token';

  final FlutterSecureStorage _storage;

  SecureStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  Future<String?> readToken() => _storage.read(key: _tokenKey);

  Future<void> writeToken(String token) =>
      _storage.write(key: _tokenKey, value: token);

  Future<void> deleteToken() => _storage.delete(key: _tokenKey);
}
