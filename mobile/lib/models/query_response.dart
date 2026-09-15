import 'agent_info.dart';
import 'audio_ref.dart';

/// Response of `POST /api/v1/query`.
class QueryResponse {
  final String requestId;
  final String conversationId;
  final String query;
  final String answer;
  final AgentInfo agent;
  final AudioRef? audio;
  final int? durationMs;

  /// The model's chain-of-thought for this turn, kept separate from
  /// [answer] -- render it as a collapsed-by-default "Thinking" section
  /// (see widgets/message_bubble.dart), not mixed into the visible
  /// response. Null when the CLI/model didn't produce one.
  final String? reasoning;

  const QueryResponse({
    required this.requestId,
    required this.conversationId,
    required this.query,
    required this.answer,
    required this.agent,
    required this.audio,
    required this.durationMs,
    this.reasoning,
  });

  factory QueryResponse.fromJson(Map<String, dynamic> json) {
    return QueryResponse(
      requestId: json['request_id'] as String? ?? '',
      conversationId: json['conversation_id'] as String? ?? '',
      query: json['query'] as String? ?? '',
      answer: json['answer'] as String? ?? '',
      agent: AgentInfo.fromJson(
        json['agent'] as Map<String, dynamic>? ?? const {},
      ),
      audio: AudioRef.fromJson(json['audio'] as Map<String, dynamic>?),
      durationMs: json['duration_ms'] as int?,
      reasoning: json['reasoning'] as String?,
    );
  }
}

/// Response of `POST /api/v1/query/audio`.
class QueryAudioResponse {
  final String requestId;
  final String conversationId;
  final String transcript;
  final String answer;
  final AgentInfo agent;
  final AudioRef? audio;
  final String? reasoning;

  const QueryAudioResponse({
    required this.requestId,
    required this.conversationId,
    required this.transcript,
    required this.answer,
    required this.agent,
    required this.audio,
    this.reasoning,
  });

  factory QueryAudioResponse.fromJson(Map<String, dynamic> json) {
    return QueryAudioResponse(
      requestId: json['request_id'] as String? ?? '',
      conversationId: json['conversation_id'] as String? ?? '',
      transcript: json['transcript'] as String? ?? '',
      answer: json['answer'] as String? ?? '',
      agent: AgentInfo.fromJson(
        json['agent'] as Map<String, dynamic>? ?? const {},
      ),
      audio: AudioRef.fromJson(json['audio'] as Map<String, dynamic>?),
      reasoning: json['reasoning'] as String?,
    );
  }
}
