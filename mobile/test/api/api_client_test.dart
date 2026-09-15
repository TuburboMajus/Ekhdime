import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:plane_assistant/api/api_client.dart';
import 'package:plane_assistant/api/api_exception.dart';

void main() {
  const baseUrl = 'http://10.0.2.2:8088';

  ApiClient clientWith(
    Future<http.Response> Function(http.Request) handler, {
    String? token = 'test-token',
  }) {
    return ApiClient(
      baseUrl: baseUrl,
      token: token,
      httpClient: MockClient(handler),
    );
  }

  group('health / info', () {
    test('health() returns true on {"status":"ok"} without auth header', () async {
      String? seenAuth;
      final client = clientWith((request) async {
        seenAuth = request.headers['Authorization'];
        expect(request.url.path, '/api/v1/health');
        return http.Response(jsonEncode({'status': 'ok'}), 200);
      });

      final result = await client.health();
      expect(result, isTrue);
      expect(seenAuth, isNull);
    });

    test('info() parses features map', () async {
      final client = clientWith((request) async {
        expect(request.url.path, '/api/v1/info');
        return http.Response(
          jsonEncode({
            'server_version': '0.1.0',
            'api_version': 'v1',
            'features': {
              'stt': true,
              'tts': true,
              'conversations': true,
              'request_cancellation': true,
            },
          }),
          200,
        );
      });

      final info = await client.info();
      expect(info.serverVersion, '0.1.0');
      expect(info.apiVersion, 'v1');
      expect(info.features['stt'], isTrue);
    });

    test('healthDetails() sends bearer token and parses nested agent_cli', () async {
      String? seenAuth;
      final client = clientWith((request) async {
        seenAuth = request.headers['Authorization'];
        return http.Response(
          jsonEncode({
            'gateway': 'ok',
            'plane': 'ok',
            'plane_mcp': 'ok',
            'stt': 'ok',
            'tts': 'error',
            'agent_cli': {'status': 'ok', 'type': 'copilot'},
          }),
          200,
        );
      });

      final details = await client.healthDetails();
      expect(seenAuth, 'Bearer test-token');
      expect(details.tts, 'error');
      expect(details.agentCli.type, 'copilot');
      expect(details.allOk, isFalse);
    });
  });

  group('query', () {
    test('query() posts expected body and parses response', () async {
      Map<String, dynamic>? sentBody;
      final client = clientWith((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/query');
        sentBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'request_id': 'req-1',
            'conversation_id': 'conv-1',
            'query': 'list my projects',
            'answer': 'You have 3 projects.',
            'agent': {'cli': 'copilot', 'model': 'deepseek-v4-pro'},
            'audio': null,
            'duration_ms': 3240,
          }),
          200,
        );
      });

      final response = await client.query(query: 'list my projects');
      expect(sentBody, {
        'query': 'list my projects',
        'conversation_id': null,
        'include_audio': false,
      });
      expect(response.answer, 'You have 3 projects.');
      expect(response.agent.cli, 'copilot');
      expect(response.audio, isNull);
      expect(response.durationMs, 3240);
    });

    test('query() parses non-null audio ref when include_audio succeeds', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'request_id': 'req-1',
            'conversation_id': 'conv-1',
            'query': 'hi',
            'answer': 'hello',
            'agent': {'cli': 'copilot'},
            'audio': {
              'available': true,
              'url': '/api/v1/audio/responses/req-1',
              'mime_type': 'audio/mpeg',
            },
            'duration_ms': 100,
          }),
          200,
        );
      });

      final response = await client.query(query: 'hi', includeAudio: true);
      expect(response.audio?.available, isTrue);
      expect(response.audio?.url, '/api/v1/audio/responses/req-1');
    });

    test('query() throws ApiException with parsed error envelope on 504', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'AGENT_TIMEOUT',
              'message': 'The AI agent did not complete within 180 seconds.',
              'request_id': 'req-err',
            },
          }),
          504,
        );
      });

      expect(
        () => client.query(query: 'hi'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.agentTimeout)
              .having((e) => e.requestId, 'requestId', 'req-err')
              .having((e) => e.statusCode, 'statusCode', 504),
        ),
      );
    });

    test('unauthorized 401 maps to ApiErrorCode.unauthorized', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'UNAUTHORIZED',
              'message': 'Missing or invalid token',
              'request_id': 'req-x',
            },
          }),
          401,
        );
      });

      expect(
        () => client.query(query: 'hi'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unauthorized)),
      );
    });

    test('unrecognized error code maps to ApiErrorCode.unknown', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'SOME_FUTURE_CODE',
              'message': 'new thing',
              'request_id': 'req-y',
            },
          }),
          418,
        );
      });

      expect(
        () => client.query(query: 'hi'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unknown)),
      );
    });

    test('malformed JSON body throws ApiException instead of crashing', () async {
      final client = clientWith((request) async {
        return http.Response('not json at all {{{', 200);
      });

      expect(
        () => client.query(query: 'hi'),
        throwsA(isA<ApiException>()),
      );
    });

    test('network failure (no response) is wrapped as ApiException', () async {
      final client = clientWith((request) async {
        throw const SocketExceptionStub('Connection refused');
      });

      expect(
        () => client.query(query: 'hi'),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('queryAudio', () {
    test('sends multipart request with expected fields', () async {
      // `MockClient`'s basic handler (package:http testing.dart) always
      // finalizes the outgoing request into a plain `Request` with the
      // encoded multipart bytes as its body -- it does not hand back the
      // original `MultipartRequest` instance -- so we assert on the
      // finalized content-type/body instead of the request's runtime type.
      final client = clientWith((request) async {
        expect(request.url.path, '/api/v1/query/audio');
        final contentType = request.headers['content-type'] ?? '';
        expect(contentType, contains('multipart/form-data'));
        final body = latin1.decode(request.bodyBytes);
        expect(body, contains('name="include_audio"'));
        expect(body, contains('true'));
        expect(body, contains('name="language"'));
        expect(body, contains('en'));
        expect(body, contains('name="file"'));
        expect(body, contains('filename="recording.m4a"'));
        return http.Response(
          jsonEncode({
            'request_id': 'r1',
            'conversation_id': 'c1',
            'transcript': 'what is next',
            'answer': 'Do ABC-42',
            'agent': {'cli': 'copilot'},
            'audio': null,
          }),
          200,
        );
      });

      final response = await client.queryAudio(
        audioBytes: Uint8List.fromList([1, 2, 3]),
        filename: 'recording.m4a',
        includeAudio: true,
        language: 'en',
      );
      expect(response.transcript, 'what is next');
      expect(response.answer, 'Do ABC-42');
    });

    test('agent failure after successful transcription carries transcript on the exception', () async {
      // Regression test: STT can succeed and get persisted server-side
      // while the agent step fails afterward -- the error envelope then
      // carries a sibling "transcript" field (see gateway/API.md) so the
      // client can still show what the user said instead of losing it.
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'AGENT_INVALID_RESPONSE',
              'message': 'leaked tool syntax',
              'request_id': 'req-z',
            },
            'transcript': 'list all my projects',
          }),
          502,
        );
      });

      expect(
        () => client.queryAudio(
          audioBytes: Uint8List.fromList([1, 2, 3]),
          filename: 'recording.m4a',
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.agentInvalidResponse)
              .having((e) => e.transcript, 'transcript', 'list all my projects'),
        ),
      );
    });

    test('EMPTY_TRANSCRIPT maps to ApiErrorCode.emptyTranscript with no transcript', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'EMPTY_TRANSCRIPT',
              'message': 'No speech was detected in that recording.',
              'request_id': 'req-w',
            },
          }),
          400,
        );
      });

      expect(
        () => client.queryAudio(
          audioBytes: Uint8List.fromList([1, 2, 3]),
          filename: 'recording.m4a',
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.emptyTranscript)
              .having((e) => e.transcript, 'transcript', isNull),
        ),
      );
    });
  });

  group('stt', () {
    test('returns transcribed text', () async {
      final client = clientWith((request) async {
        expect(request.url.path, '/api/v1/stt');
        return http.Response(jsonEncode({'text': 'move task ABC-42 to done'}), 200);
      });

      final text = await client.stt(
        audioBytes: Uint8List.fromList([1, 2, 3]),
        filename: 'a.m4a',
      );
      expect(text, 'move task ABC-42 to done');
    });

    test('503 STT_UNAVAILABLE maps correctly', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'STT_UNAVAILABLE',
              'message': 'Whisper is down',
              'request_id': 'r2',
            },
          }),
          503,
        );
      });

      expect(
        () => client.stt(audioBytes: Uint8List.fromList([1]), filename: 'a.m4a'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.sttUnavailable)),
      );
    });
  });

  group('tts', () {
    test('returns raw audio bytes on 200', () async {
      final bytes = Uint8List.fromList([0xff, 0xfb, 0x90, 0x00]);
      final client = clientWith((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/tts');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['text'], 'hello');
        expect(body['format'], 'mp3');
        return http.Response.bytes(bytes, 200, headers: {'content-type': 'audio/mpeg'});
      });

      final result = await client.tts(text: 'hello');
      expect(result, bytes);
    });

    test('TTS_UNAVAILABLE error surfaces as ApiException', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'TTS_UNAVAILABLE',
              'message': 'Kokoro is down',
              'request_id': 'r3',
            },
          }),
          503,
        );
      });

      expect(
        () => client.tts(text: 'hello'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.ttsUnavailable)),
      );
    });
  });

  group('ttsVoices', () {
    test('parses voices list and default', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'voices': ['af_heart', 'af_bella', 'am_adam'],
            'default': 'af_heart',
          }),
          200,
        );
      });

      final result = await client.ttsVoices();
      expect(result.voices, ['af_heart', 'af_bella', 'am_adam']);
      expect(result.defaultVoice, 'af_heart');
    });
  });

  group('conversations', () {
    test('listConversations parses list', () async {
      final client = clientWith((request) async {
        expect(request.url.path, '/api/v1/conversations');
        return http.Response(
          jsonEncode({
            'conversations': [
              {
                'id': 'c1',
                'title': 'Sprint planning',
                'created_at': '2026-09-01T10:00:00Z',
                'updated_at': '2026-09-01T10:05:00Z',
              },
              {
                'id': 'c2',
                'title': null,
                'created_at': '2026-09-02T10:00:00Z',
                'updated_at': '2026-09-02T10:05:00Z',
              },
            ],
          }),
          200,
        );
      });

      final result = await client.listConversations();
      expect(result, hasLength(2));
      expect(result[0].title, 'Sprint planning');
      expect(result[1].title, isNull);
    });

    test('createConversation posts title and returns 201 body', () async {
      final client = clientWith((request) async {
        expect(request.method, 'POST');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['title'], 'My conversation');
        return http.Response(
          jsonEncode({
            'id': 'c3',
            'title': 'My conversation',
            'created_at': '2026-09-01T10:00:00Z',
            'updated_at': '2026-09-01T10:00:00Z',
          }),
          201,
        );
      });

      final conv = await client.createConversation(title: 'My conversation');
      expect(conv.id, 'c3');
    });

    test('getConversation parses messages', () async {
      final client = clientWith((request) async {
        expect(request.url.path, '/api/v1/conversations/c1');
        return http.Response(
          jsonEncode({
            'id': 'c1',
            'title': 'Sprint planning',
            'created_at': '2026-09-01T10:00:00Z',
            'updated_at': '2026-09-01T10:05:00Z',
            'messages': [
              {
                'id': 'm1',
                'role': 'user',
                'content': 'What should I work on today?',
                'created_at': '2026-09-01T10:00:00Z',
                'metadata': {},
              },
              {
                'id': 'm2',
                'role': 'assistant',
                'content': 'ABC-42.',
                'created_at': '2026-09-01T10:00:05Z',
                'metadata': {'tools_used': ['plane.list_issues']},
              },
            ],
          }),
          200,
        );
      });

      final detail = await client.getConversation('c1');
      expect(detail.messages, hasLength(2));
      expect(detail.messages[1].content, 'ABC-42.');
    });

    test('getConversation 404 maps to notFound', () async {
      final client = clientWith((request) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'NOT_FOUND',
              'message': 'no such conversation',
              'request_id': 'r4',
            },
          }),
          404,
        );
      });

      expect(
        () => client.getConversation('missing'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.notFound)),
      );
    });

    test('deleteConversation succeeds on 204 with empty body', () async {
      final client = clientWith((request) async {
        expect(request.method, 'DELETE');
        return http.Response('', 204);
      });

      await client.deleteConversation('c1');
    });
  });

  group('cancelRequest', () {
    test('DELETE /requests/{id} returns cancelled flag', () async {
      final client = clientWith((request) async {
        expect(request.method, 'DELETE');
        expect(request.url.path, '/api/v1/requests/req-1');
        return http.Response(jsonEncode({'cancelled': true}), 202);
      });

      final cancelled = await client.cancelRequest('req-1');
      expect(cancelled, isTrue);
    });
  });

  group('base URL handling', () {
    test('does not double up slashes when path already has leading slash', () async {
      final client = ApiClient(
        baseUrl: 'http://10.0.2.2:8088',
        token: 't',
        httpClient: MockClient((request) async {
          expect(request.url.toString(), 'http://10.0.2.2:8088/api/v1/health');
          return http.Response(jsonEncode({'status': 'ok'}), 200);
        }),
      );
      await client.health();
    });
  });
}

/// Minimal stand-in for a low-level socket error thrown by the underlying
/// HTTP stack, used to verify [ApiClient] wraps *any* thrown exception (not
/// just [ApiException]) into an [ApiException.network].
class SocketExceptionStub implements Exception {
  final String message;
  const SocketExceptionStub(this.message);
  @override
  String toString() => 'SocketExceptionStub: $message';
}
