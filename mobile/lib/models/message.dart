enum MessageRole {
  user,
  assistant;

  static MessageRole fromWire(String? value) {
    switch (value) {
      case 'assistant':
        return MessageRole.assistant;
      case 'user':
      default:
        return MessageRole.user;
    }
  }

  String toWire() => this == MessageRole.assistant ? 'assistant' : 'user';
}

/// A single message within a conversation, either persisted server-side
/// (returned from `GET /api/v1/conversations/{id}`) or created locally for
/// optimistic UI while a query is in flight.
class Message {
  final String id;
  final MessageRole role;
  final String content;
  final DateTime createdAt;
  final Map<String, dynamic> metadata;

  /// The original query text/transcript that produced this message, used to
  /// support the "Retry" action on assistant messages. Only set on
  /// assistant messages created client-side during this session.
  final String? sourceQuery;

  /// Set while an assistant message is a placeholder awaiting a response.
  final bool isPending;

  /// Set when the query/response that produced this message failed.
  final bool isError;

  /// Set on a user message whose content came from a voice recording
  /// (transcribed server-side) rather than typed text -- rendered with a
  /// mic hint so it reads distinctly in the conversation. Never set on
  /// assistant messages.
  final bool isVoiceInput;

  /// The model's chain-of-thought for this turn, when the server captured
  /// one (stored server-side inside the generic [metadata] map under the
  /// "reasoning" key -- see gateway/API.md). Render collapsed by default,
  /// separate from [content].
  String? get reasoning => metadata['reasoning'] as String?;

  const Message({
    required this.id,
    required this.role,
    required this.content,
    required this.createdAt,
    this.metadata = const {},
    this.sourceQuery,
    this.isPending = false,
    this.isError = false,
    this.isVoiceInput = false,
  });

  factory Message.fromJson(Map<String, dynamic> json) {
    return Message(
      id: json['id'] as String? ?? '',
      role: MessageRole.fromWire(json['role'] as String?),
      content: json['content'] as String? ?? '',
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ??
              DateTime.now(),
      metadata: (json['metadata'] as Map<String, dynamic>?) ?? const {},
    );
  }

  Message copyWith({
    String? id,
    MessageRole? role,
    String? content,
    DateTime? createdAt,
    Map<String, dynamic>? metadata,
    String? sourceQuery,
    bool? isPending,
    bool? isError,
    bool? isVoiceInput,
  }) {
    return Message(
      id: id ?? this.id,
      role: role ?? this.role,
      content: content ?? this.content,
      createdAt: createdAt ?? this.createdAt,
      metadata: metadata ?? this.metadata,
      sourceQuery: sourceQuery ?? this.sourceQuery,
      isPending: isPending ?? this.isPending,
      isError: isError ?? this.isError,
      isVoiceInput: isVoiceInput ?? this.isVoiceInput,
    );
  }
}
