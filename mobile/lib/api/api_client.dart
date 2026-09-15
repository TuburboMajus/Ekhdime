import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../models/conversation.dart';
import '../models/health.dart';
import '../models/query_response.dart';
import 'api_exception.dart';

/// Thin, typed wrapper around every endpoint in the gateway's `/api/v1`
/// contract (see gateway/API.md). Every method throws [ApiException] on
/// error: a well-formed error envelope, a network failure, a timeout, or an
/// unparseable response. Callers never need to touch `http` directly.
class ApiClient {
  /// Base URL, already normalized (no trailing slash) by [ServerUrl.normalize].
  final String baseUrl;

  /// Bearer token. May be null/empty for the two unauthenticated endpoints.
  final String? token;

  final http.Client _http;
  final Duration timeout;

  /// Timeout for `/query` and `/query/audio` specifically. `/query/audio`
  /// runs STT -> agent CLI -> MCP -> Plane -> (TTS) *sequentially* with no
  /// overall per-request deadline server-side, so the worst case is the sum
  /// of every stage's own timeout, not just the agent's: gateway defaults
  /// are STT 60s + agent 300s + TTS 60s = 420s. Using a shorter timeout
  /// here (previously 360s, still less than that 420s worst case) made the
  /// app give up client-side on a voice query with audio playback enabled
  /// while the server was still legitimately working -- found against a
  /// real deployment. Kept comfortably above that 420s worst case, with
  /// margin for network/upload overhead on top. See
  /// gateway/tests/test_config.py's matching invariant test -- keep both in
  /// sync by hand if the gateway's stage timeouts change.
  final Duration queryTimeout;

  ApiClient({
    required this.baseUrl,
    this.token,
    http.Client? httpClient,
    this.timeout = const Duration(seconds: 30),
    this.queryTimeout = const Duration(seconds: 480),
  }) : _http = httpClient ?? http.Client();

  Uri _uri(String path, [Map<String, String>? query]) {
    return Uri.parse('$baseUrl$path').replace(
      queryParameters: query != null && query.isNotEmpty ? query : null,
    );
  }

  Map<String, String> _headers({bool auth = true, bool json = true}) {
    final headers = <String, String>{'Accept': 'application/json'};
    if (json) headers['Content-Type'] = 'application/json';
    if (auth && token != null && token!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<http.Response> _send(
    Future<http.Response> Function() fn, {
    Duration? timeoutOverride,
  }) async {
    try {
      return await fn().timeout(timeoutOverride ?? timeout);
    } on TimeoutException {
      throw ApiException.timeout();
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException.network(e.toString());
    }
  }

  /// Decodes a JSON response body, throwing [ApiException] for non-2xx
  /// responses (parsing the error envelope when present) or malformed JSON.
  dynamic _decode(http.Response response) {
    Map<String, dynamic>? body;
    if (response.bodyBytes.isNotEmpty) {
      try {
        final decoded = jsonDecode(utf8.decode(response.bodyBytes));
        if (decoded is Map<String, dynamic>) {
          body = decoded;
        } else {
          if (response.statusCode >= 200 && response.statusCode < 300) {
            return decoded;
          }
          throw ApiException.malformedResponse(
            'Unexpected response shape from server.',
          );
        }
      } on ApiException {
        rethrow;
      } catch (_) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          throw ApiException.malformedResponse(
            'Server returned a response that could not be parsed.',
          );
        }
        throw ApiException(
          code: ApiErrorCode.unknown,
          message: 'Server error (${response.statusCode}).',
          statusCode: response.statusCode,
        );
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body ?? const <String, dynamic>{};
    }

    final errorField = body?['error'];
    if (errorField is Map<String, dynamic>) {
      throw ApiException(
        code: ApiErrorCode.fromWire(errorField['code'] as String?),
        message: errorField['message'] as String? ??
            'Something went wrong (${response.statusCode}).',
        requestId: errorField['request_id'] as String?,
        statusCode: response.statusCode,
        // /query/audio only: set when STT succeeded before something later
        // failed -- see gateway/API.md's "transcript" sibling field.
        transcript: body?['transcript'] as String?,
      );
    }

    throw ApiException(
      code: ApiErrorCode.unknown,
      message: 'Server error (${response.statusCode}).',
      statusCode: response.statusCode,
    );
  }

  // ---------------------------------------------------------------------
  // Health / info
  // ---------------------------------------------------------------------

  /// `GET /api/v1/health`. No auth. Returns true if the server replied
  /// `{"status": "ok"}`.
  Future<bool> health() async {
    final response = await _send(
      () => _http.get(_uri('/api/v1/health'), headers: _headers(auth: false, json: false)),
    );
    final json = _decode(response) as Map<String, dynamic>;
    return json['status'] == 'ok';
  }

  /// `GET /api/v1/info`. No auth.
  Future<ServerInfo> info() async {
    final response = await _send(
      () => _http.get(_uri('/api/v1/info'), headers: _headers(auth: false, json: false)),
    );
    return ServerInfo.fromJson(_decode(response) as Map<String, dynamic>);
  }

  /// `GET /api/v1/health/details`. Auth required.
  Future<HealthDetails> healthDetails() async {
    final response = await _send(
      () => _http.get(_uri('/api/v1/health/details'), headers: _headers(json: false)),
    );
    return HealthDetails.fromJson(_decode(response) as Map<String, dynamic>);
  }

  // ---------------------------------------------------------------------
  // Query
  // ---------------------------------------------------------------------

  /// `POST /api/v1/query`.
  Future<QueryResponse> query({
    required String query,
    String? conversationId,
    bool includeAudio = false,
  }) async {
    final response = await _send(
      () => _http.post(
        _uri('/api/v1/query'),
        headers: _headers(),
        body: jsonEncode({
          'query': query,
          'conversation_id': conversationId,
          'include_audio': includeAudio,
        }),
      ),
      timeoutOverride: queryTimeout,
    );
    return QueryResponse.fromJson(_decode(response) as Map<String, dynamic>);
  }

  /// `POST /api/v1/query/audio`. `audioBytes` should be the raw contents of
  /// a recorded audio file; `filename` should carry a recognizable extension
  /// (e.g. `recording.m4a`).
  Future<QueryAudioResponse> queryAudio({
    required Uint8List audioBytes,
    required String filename,
    String? conversationId,
    bool includeAudio = false,
    String? language,
  }) async {
    final response = await _send(() async {
      final request = http.MultipartRequest('POST', _uri('/api/v1/query/audio'));
      request.headers.addAll(_headers(json: false));
      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          audioBytes,
          filename: filename,
          contentType: _audioContentType(filename),
        ),
      );
      if (conversationId != null) {
        request.fields['conversation_id'] = conversationId;
      }
      request.fields['include_audio'] = includeAudio.toString();
      if (language != null) {
        request.fields['language'] = language;
      }
      final streamed = await _http.send(request);
      return http.Response.fromStream(streamed);
    }, timeoutOverride: queryTimeout);
    return QueryAudioResponse.fromJson(_decode(response) as Map<String, dynamic>);
  }

  // ---------------------------------------------------------------------
  // STT / TTS
  // ---------------------------------------------------------------------

  /// `POST /api/v1/stt`. Transcription only, no agent call.
  Future<String> stt({required Uint8List audioBytes, required String filename, String? language}) async {
    final response = await _send(() async {
      final request = http.MultipartRequest('POST', _uri('/api/v1/stt'));
      request.headers.addAll(_headers(json: false));
      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          audioBytes,
          filename: filename,
          contentType: _audioContentType(filename),
        ),
      );
      if (language != null) {
        request.fields['language'] = language;
      }
      final streamed = await _http.send(request);
      return http.Response.fromStream(streamed);
    });
    final json = _decode(response) as Map<String, dynamic>;
    return json['text'] as String? ?? '';
  }

  /// `POST /api/v1/tts`. Returns raw audio bytes on success.
  Future<Uint8List> tts({
    required String text,
    String? voice,
    String format = 'mp3',
    double speed = 1.0,
  }) async {
    final response = await _send(
      () => _http.post(
        _uri('/api/v1/tts'),
        headers: {..._headers(), 'Accept': 'audio/*'},
        body: jsonEncode({
          'text': text,
          'voice': voice,
          'format': format,
          'speed': speed,
        }),
      ),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.bodyBytes;
    }
    _decode(response);
    // _decode always throws for non-2xx; this is unreachable but keeps the
    // analyzer happy about a guaranteed return.
    throw ApiException.malformedResponse('Unexpected TTS response.');
  }

  /// `GET /api/v1/tts/voices`.
  Future<VoiceList> ttsVoices() async {
    final response = await _send(
      () => _http.get(_uri('/api/v1/tts/voices'), headers: _headers(json: false)),
    );
    return VoiceList.fromJson(_decode(response) as Map<String, dynamic>);
  }

  /// `GET /api/v1/audio/responses/{id}`. `id` is the opaque id from an
  /// [AudioRef.url] (e.g. `/api/v1/audio/responses/<id>`); pass either the
  /// bare id or the full path -- both are accepted.
  Future<Uint8List> audioResponse(String idOrPath) async {
    final path = idOrPath.startsWith('/')
        ? idOrPath
        : '/api/v1/audio/responses/$idOrPath';
    final response = await _send(
      () => _http.get(_uri(path), headers: {..._headers(json: false), 'Accept': 'audio/*'}),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.bodyBytes;
    }
    _decode(response);
    throw ApiException.malformedResponse('Unexpected audio response.');
  }

  // ---------------------------------------------------------------------
  // Conversations
  // ---------------------------------------------------------------------

  /// `GET /api/v1/conversations`.
  Future<List<Conversation>> listConversations() async {
    final response = await _send(
      () => _http.get(_uri('/api/v1/conversations'), headers: _headers(json: false)),
    );
    final json = _decode(response) as Map<String, dynamic>;
    final raw = json['conversations'] as List<dynamic>? ?? const [];
    return raw
        .map((c) => Conversation.fromJson(c as Map<String, dynamic>))
        .toList();
  }

  /// `POST /api/v1/conversations`.
  Future<Conversation> createConversation({String? title}) async {
    final response = await _send(
      () => _http.post(
        _uri('/api/v1/conversations'),
        headers: _headers(),
        body: jsonEncode({'title': title}),
      ),
    );
    return Conversation.fromJson(_decode(response) as Map<String, dynamic>);
  }

  /// `GET /api/v1/conversations/{id}`.
  Future<ConversationDetail> getConversation(String id) async {
    final response = await _send(
      () => _http.get(_uri('/api/v1/conversations/$id'), headers: _headers(json: false)),
    );
    return ConversationDetail.fromJson(_decode(response) as Map<String, dynamic>);
  }

  /// `DELETE /api/v1/conversations/{id}`. Idempotent; succeeds even if the
  /// conversation is already gone.
  Future<void> deleteConversation(String id) async {
    final response = await _send(
      () => _http.delete(_uri('/api/v1/conversations/$id'), headers: _headers(json: false)),
    );
    if (response.statusCode == 204) return;
    _decode(response);
  }

  // ---------------------------------------------------------------------
  // Requests
  // ---------------------------------------------------------------------

  /// `DELETE /api/v1/requests/{id}`. Best-effort cancellation; returns
  /// whether the server actually cancelled anything.
  Future<bool> cancelRequest(String requestId) async {
    final response = await _send(
      () => _http.delete(_uri('/api/v1/requests/$requestId'), headers: _headers(json: false)),
    );
    final json = _decode(response) as Map<String, dynamic>;
    return json['cancelled'] == true;
  }

  void close() => _http.close();
}

/// `http.MultipartFile.fromBytes` defaults to `application/octet-stream`
/// when no `contentType` is given -- confirmed in the `http` package source
/// (multipart_file.dart), which even has an unimplemented
/// `// TODO: Infer the content-type from the filename`. Left unset, every
/// audio upload was silently rejected by the gateway's content-type
/// whitelist before ever reaching Whisper (`INVALID_REQUEST`, "That request
/// was not valid"), found by checking the gateway's own logs against a real
/// device recording. Recordings always come from [AudioRecorderService]
/// with a `.m4a` extension (see its `AudioEncoder.aacLc` config), but this
/// maps a couple of other extensions too in case a file ever arrives from
/// elsewhere (e.g. a future "attach a file" flow).
MediaType _audioContentType(String filename) {
  final ext = filename.contains('.') ? filename.split('.').last.toLowerCase() : '';
  switch (ext) {
    case 'm4a':
    case 'mp4':
      return MediaType('audio', 'mp4');
    case 'wav':
      return MediaType('audio', 'wav');
    case 'mp3':
      return MediaType('audio', 'mpeg');
    case 'aac':
      return MediaType('audio', 'aac');
    case 'ogg':
      return MediaType('audio', 'ogg');
    case 'webm':
      return MediaType('audio', 'webm');
    default:
      return MediaType('audio', 'mp4');
  }
}

/// Response of `GET /api/v1/tts/voices`.
class VoiceList {
  final List<String> voices;
  final String? defaultVoice;

  const VoiceList({required this.voices, required this.defaultVoice});

  factory VoiceList.fromJson(Map<String, dynamic> json) {
    final raw = json['voices'] as List<dynamic>? ?? const [];
    return VoiceList(
      voices: raw.map((v) => v.toString()).toList(),
      defaultVoice: json['default'] as String?,
    );
  }
}
