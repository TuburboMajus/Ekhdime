/// Reference to server-synthesized audio, returned alongside a query
/// response when `include_audio` was requested and synthesis succeeded.
class AudioRef {
  final bool available;
  final String url;
  final String mimeType;

  const AudioRef({
    required this.available,
    required this.url,
    required this.mimeType,
  });

  static AudioRef? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    return AudioRef(
      available: json['available'] as bool? ?? false,
      url: json['url'] as String? ?? '',
      mimeType: json['mime_type'] as String? ?? 'audio/mpeg',
    );
  }

  Map<String, dynamic> toJson() => {
        'available': available,
        'url': url,
        'mime_type': mimeType,
      };
}
