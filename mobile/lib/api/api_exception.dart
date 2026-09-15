/// Error codes defined by the gateway API contract.
///
/// See gateway/API.md for the authoritative list. `UNKNOWN` is a client-side
/// fallback for codes the app doesn't recognize (e.g. a future server
/// version added a new one).
enum ApiErrorCode {
  unauthorized,
  invalidRequest,
  notFound,
  audioTooLarge,
  sttUnavailable,
  ttsUnavailable,
  mcpUnavailable,
  planeUnavailable,
  agentUnavailable,
  agentTimeout,
  agentInvalidResponse,
  emptyTranscript,
  llmAuthenticationError,
  llmRateLimited,
  internalError,
  unknown;

  static ApiErrorCode fromWire(String? code) {
    switch (code) {
      case 'UNAUTHORIZED':
        return ApiErrorCode.unauthorized;
      case 'INVALID_REQUEST':
        return ApiErrorCode.invalidRequest;
      case 'NOT_FOUND':
        return ApiErrorCode.notFound;
      case 'AUDIO_TOO_LARGE':
        return ApiErrorCode.audioTooLarge;
      case 'STT_UNAVAILABLE':
        return ApiErrorCode.sttUnavailable;
      case 'TTS_UNAVAILABLE':
        return ApiErrorCode.ttsUnavailable;
      case 'MCP_UNAVAILABLE':
        return ApiErrorCode.mcpUnavailable;
      case 'PLANE_UNAVAILABLE':
        return ApiErrorCode.planeUnavailable;
      case 'AGENT_UNAVAILABLE':
        return ApiErrorCode.agentUnavailable;
      case 'AGENT_TIMEOUT':
        return ApiErrorCode.agentTimeout;
      case 'AGENT_INVALID_RESPONSE':
        return ApiErrorCode.agentInvalidResponse;
      case 'EMPTY_TRANSCRIPT':
        return ApiErrorCode.emptyTranscript;
      case 'LLM_AUTHENTICATION_ERROR':
        return ApiErrorCode.llmAuthenticationError;
      case 'LLM_RATE_LIMITED':
        return ApiErrorCode.llmRateLimited;
      case 'INTERNAL_ERROR':
        return ApiErrorCode.internalError;
      default:
        return ApiErrorCode.unknown;
    }
  }
}

/// Thrown by [ApiClient] for any error condition: a well-formed error
/// envelope from the gateway, a network failure, a timeout, or an
/// unparseable response. Callers should branch on [code] to show a
/// user-facing message (see `ApiErrorCode` -> message mapping in the UI
/// layer) rather than displaying [message] directly, since [message] may
/// be a raw exception string for non-envelope failures.
class ApiException implements Exception {
  final ApiErrorCode code;
  final String message;
  final String? requestId;
  final int? statusCode;

  /// Set only for `/query/audio` failures where transcription succeeded
  /// before something later failed (see gateway/API.md's `transcript`
  /// sibling field) -- callers can still show what the user said instead
  /// of losing it behind a bare error. Null for every other failure.
  final String? transcript;

  const ApiException({
    required this.code,
    required this.message,
    this.requestId,
    this.statusCode,
    this.transcript,
  });

  /// A network-level failure (no HTTP response at all): connection refused,
  /// DNS failure, socket error, etc.
  factory ApiException.network(String message) => ApiException(
        code: ApiErrorCode.unknown,
        message: message,
      );

  /// The request exceeded the client-side timeout.
  factory ApiException.timeout() => const ApiException(
        code: ApiErrorCode.agentTimeout,
        message: 'The request timed out.',
      );

  /// The response body was not valid JSON, or didn't match the expected
  /// envelope/shape.
  factory ApiException.malformedResponse(String message) => ApiException(
        code: ApiErrorCode.unknown,
        message: message,
      );

  @override
  String toString() => 'ApiException(code: $code, message: $message)';
}
