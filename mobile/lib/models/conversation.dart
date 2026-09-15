import 'message.dart';

/// A conversation summary as returned in `GET /api/v1/conversations` list
/// items and `POST /api/v1/conversations`.
class Conversation {
  final String id;
  final String? title;
  final DateTime createdAt;
  final DateTime updatedAt;

  const Conversation({
    required this.id,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Conversation.fromJson(Map<String, dynamic> json) {
    return Conversation(
      id: json['id'] as String? ?? '',
      title: json['title'] as String?,
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ??
              DateTime.now(),
      updatedAt:
          DateTime.tryParse(json['updated_at'] as String? ?? '') ??
              DateTime.now(),
    );
  }
}

/// Full conversation detail as returned by `GET /api/v1/conversations/{id}`.
class ConversationDetail {
  final String id;
  final String? title;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<Message> messages;

  const ConversationDetail({
    required this.id,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
    required this.messages,
  });

  factory ConversationDetail.fromJson(Map<String, dynamic> json) {
    final rawMessages = json['messages'] as List<dynamic>? ?? const [];
    return ConversationDetail(
      id: json['id'] as String? ?? '',
      title: json['title'] as String?,
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ??
              DateTime.now(),
      updatedAt:
          DateTime.tryParse(json['updated_at'] as String? ?? '') ??
              DateTime.now(),
      messages: rawMessages
          .map((m) => Message.fromJson(m as Map<String, dynamic>))
          .toList(),
    );
  }
}
