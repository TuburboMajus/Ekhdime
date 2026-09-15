import 'api_exception.dart';

/// Maps [ApiErrorCode] to a short, user-facing message. Centralized so
/// every screen shows consistent wording instead of raw server text.
String userMessageFor(ApiException error) {
  switch (error.code) {
    case ApiErrorCode.unauthorized:
      return 'Your API token was rejected. Please sign in again.';
    case ApiErrorCode.invalidRequest:
      return 'That request was not valid. Please try again.';
    case ApiErrorCode.notFound:
      return 'That item could not be found. It may have been deleted.';
    case ApiErrorCode.audioTooLarge:
      return 'That recording is too large. Try a shorter clip.';
    case ApiErrorCode.sttUnavailable:
      return 'Speech-to-text is unavailable right now. Please try again shortly.';
    case ApiErrorCode.ttsUnavailable:
      return 'Text-to-speech is unavailable right now. Please try again shortly.';
    case ApiErrorCode.mcpUnavailable:
      return 'The assistant\'s tool connection is unavailable right now.';
    case ApiErrorCode.planeUnavailable:
      return 'Plane is unreachable right now. Please try again shortly.';
    case ApiErrorCode.agentUnavailable:
      return 'The AI agent is unavailable right now. Please try again shortly.';
    case ApiErrorCode.agentTimeout:
      return 'The assistant took too long to respond. Please try again.';
    case ApiErrorCode.agentInvalidResponse:
      return 'The assistant got confused and couldn\'t give a real answer. Please try again.';
    case ApiErrorCode.emptyTranscript:
      return 'Didn\'t catch any speech in that recording. Try again in a quieter spot, '
          'or speak a bit closer to the mic.';
    case ApiErrorCode.llmAuthenticationError:
      return 'The server\'s AI provider credentials were rejected. Contact your administrator.';
    case ApiErrorCode.llmRateLimited:
      return 'The AI provider is rate-limiting requests. Please wait a moment and try again.';
    case ApiErrorCode.internalError:
      return 'Something went wrong on the server. Please try again.';
    case ApiErrorCode.unknown:
      return _fallbackMessage(error);
  }
}

String _fallbackMessage(ApiException error) {
  if (error.statusCode == null) {
    return 'Could not reach the server. Check your connection and server URL.';
  }
  return 'Unexpected error. Please try again.';
}
