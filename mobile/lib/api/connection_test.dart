import 'api_client.dart';
import 'api_exception.dart';

/// Result of a connection test against a candidate server URL/token pair.
enum ConnectionStatus {
  /// `/health/details` succeeded with the given token.
  connected,

  /// The server responded, but the token was rejected (401). Distinguished
  /// from [unreachable] by falling back to the unauthenticated `/health`
  /// endpoint.
  authenticationFailed,

  /// Neither `/health/details` nor the unauthenticated `/health` fallback
  /// succeeded -- the server itself could not be reached.
  unreachable,
}

class ConnectionTestResult {
  final ConnectionStatus status;
  final String? detail;

  const ConnectionTestResult(this.status, [this.detail]);
}

/// Tests connectivity + auth against [baseUrl] using [token], per the
/// server-setup flow: try the authenticated health-details endpoint first;
/// if that comes back `UNAUTHORIZED`, fall back to the unauthenticated
/// `/health` endpoint to tell "bad token" apart from "server unreachable".
Future<ConnectionTestResult> testConnection({
  required String baseUrl,
  required String token,
}) async {
  final authedClient = ApiClient(baseUrl: baseUrl, token: token);
  try {
    await authedClient.healthDetails();
    return const ConnectionTestResult(ConnectionStatus.connected);
  } on ApiException catch (e) {
    if (e.code == ApiErrorCode.unauthorized || e.statusCode == 401) {
      // Distinguish "bad token" from "server unreachable" by hitting the
      // unauthenticated endpoint.
      final anonClient = ApiClient(baseUrl: baseUrl);
      try {
        final ok = await anonClient.health();
        return ConnectionTestResult(
          ok ? ConnectionStatus.authenticationFailed : ConnectionStatus.unreachable,
        );
      } on ApiException {
        return const ConnectionTestResult(ConnectionStatus.unreachable);
      } finally {
        anonClient.close();
      }
    }
    return ConnectionTestResult(ConnectionStatus.unreachable, e.message);
  } finally {
    authedClient.close();
  }
}
