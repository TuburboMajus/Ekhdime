import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../api/api_exception.dart';
import '../api/error_messages.dart';
import '../models/message.dart';
import '../services/audio_player_service.dart';
import '../services/audio_recorder_service.dart';
import '../storage/app_preferences.dart';
import '../storage/secure_storage.dart';
import '../widgets/message_bubble.dart';
import '../widgets/recording_sheet.dart';
import 'server_setup_screen.dart';
import 'settings_screen.dart';

/// The main conversation screen: message history, text input, mic button,
/// and per-message actions (copy/speak/retry).
class ConversationScreen extends StatefulWidget {
  final AppPreferences preferences;
  final SecureStorage secureStorage;

  const ConversationScreen({
    super.key,
    required this.preferences,
    required this.secureStorage,
  });

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends State<ConversationScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  final _uuid = const Uuid();

  ApiClient? _client;
  final List<Message> _messages = [];
  String? _conversationId;
  bool _sending = false;
  String? _speakingMessageId;

  late final AudioRecorderService _recorder;
  late final AudioPlayerService _player;

  @override
  void initState() {
    super.initState();
    _recorder = AudioRecorderService();
    _player = AudioPlayerService();
    _conversationId = widget.preferences.lastConversationId;
    _initClient();
  }

  Future<void> _initClient() async {
    final baseUrl = widget.preferences.serverUrl;
    final token = await widget.secureStorage.readToken();
    if (baseUrl == null) {
      _routeToServerSetup();
      return;
    }
    setState(() {
      _client = ApiClient(baseUrl: baseUrl, token: token);
    });
  }

  void _routeToServerSetup() {
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => ServerSetupScreen(
          preferences: widget.preferences,
          secureStorage: widget.secureStorage,
        ),
      ),
    );
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    _recorder.dispose();
    _player.dispose();
    _client?.close();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _newConversation() async {
    setState(() {
      _messages.clear();
      _conversationId = null;
    });
    await widget.preferences.setLastConversationId(null);
  }

  Future<void> _sendQuery(String text) async {
    if (text.trim().isEmpty || _client == null) return;
    final userMessage = Message(
      id: _uuid.v4(),
      role: MessageRole.user,
      content: text,
      createdAt: DateTime.now(),
    );
    final pendingId = _uuid.v4();
    final pendingMessage = Message(
      id: pendingId,
      role: MessageRole.assistant,
      content: '',
      createdAt: DateTime.now(),
      isPending: true,
      sourceQuery: text,
    );

    setState(() {
      _messages.add(userMessage);
      _messages.add(pendingMessage);
      _sending = true;
    });
    _scrollToBottom();

    try {
      final response = await _client!.query(
        query: text,
        conversationId: _conversationId,
        includeAudio: widget.preferences.autoPlayResponses,
      );
      _conversationId = response.conversationId;
      await widget.preferences.setLastConversationId(_conversationId);

      _replacePending(
        pendingId,
        Message(
          id: response.requestId,
          role: MessageRole.assistant,
          content: response.answer,
          createdAt: DateTime.now(),
          sourceQuery: text,
          metadata: response.reasoning != null
              ? {'reasoning': response.reasoning}
              : const {},
        ),
      );

      if (widget.preferences.autoPlayResponses && response.audio != null) {
        _playServerAudio(response.audio!.url);
      }
    } on ApiException catch (e) {
      _handleError(e, pendingId, text);
    } catch (e) {
      _replacePending(
        pendingId,
        Message(
          id: pendingId,
          role: MessageRole.assistant,
          content: 'Something went wrong. Please try again.',
          createdAt: DateTime.now(),
          isError: true,
          sourceQuery: text,
        ),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToBottom();
    }
  }

  void _handleError(ApiException e, String pendingId, String sourceQuery) {
    _replacePending(
      pendingId,
      Message(
        id: pendingId,
        role: MessageRole.assistant,
        content: userMessageFor(e),
        createdAt: DateTime.now(),
        isError: true,
        sourceQuery: sourceQuery,
      ),
    );
    if (e.code == ApiErrorCode.unauthorized) {
      _routeToServerSetup();
    }
  }

  void _replacePending(String id, Message replacement) {
    if (!mounted) return;
    setState(() {
      final index = _messages.indexWhere((m) => m.id == id);
      if (index != -1) {
        _messages[index] = replacement;
      } else {
        _messages.add(replacement);
      }
    });
  }

  Future<void> _playServerAudio(String url) async {
    if (_client == null) return;
    try {
      final bytes = await _client!.audioResponse(url);
      await _player.playBytes(bytes);
    } catch (_) {
      // Audio playback is best-effort; ignore failures silently here since
      // the text answer is already shown.
    }
  }

  Future<void> _speak(Message message) async {
    if (_client == null) return;
    setState(() => _speakingMessageId = message.id);
    try {
      final bytes = await _client!.tts(text: message.content);
      await _player.playBytes(bytes);
    } on ApiException catch (e) {
      _showSnack(userMessageFor(e));
    } catch (_) {
      _showSnack('Could not play audio.');
    } finally {
      if (mounted) setState(() => _speakingMessageId = null);
    }
  }

  void _copy(Message message) {
    Clipboard.setData(ClipboardData(text: message.content));
    _showSnack('Copied to clipboard.');
  }

  void _retry(Message message) {
    final query = message.sourceQuery;
    if (query == null) return;
    setState(() => _messages.removeWhere((m) => m.id == message.id));
    _sendQuery(query);
  }

  void _showSnack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _startRecording() async {
    final status = await Permission.microphone.request();
    if (!status.isGranted) {
      if (!mounted) return;
      _showPermissionDeniedDialog();
      return;
    }
    if (!mounted) return;
    final result = await RecordingSheet.show(
      context,
      recorder: _recorder,
      player: _player,
    );
    if (result != null) {
      await _sendAudio(result.path);
    }
  }

  void _showPermissionDeniedDialog() {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Microphone access needed'),
        content: const Text(
          'Plane Assistant needs microphone access to record voice queries. '
          'Please enable it in system settings.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.of(context).pop();
              openAppSettings();
            },
            child: const Text('Open Settings'),
          ),
        ],
      ),
    );
  }

  Future<void> _sendAudio(String path) async {
    if (_client == null) return;
    final file = File(path);
    final bytes = await file.readAsBytes();

    final pendingId = _uuid.v4();
    setState(() {
      _messages.add(Message(
        id: pendingId,
        role: MessageRole.assistant,
        content: '',
        createdAt: DateTime.now(),
        isPending: true,
      ));
      _sending = true;
    });
    _scrollToBottom();

    try {
      final response = await _client!.queryAudio(
        audioBytes: bytes,
        filename: 'recording.m4a',
        conversationId: _conversationId,
        includeAudio: widget.preferences.autoPlayResponses,
        language: widget.preferences.inputLanguage,
      );
      _conversationId = response.conversationId;
      await widget.preferences.setLastConversationId(_conversationId);

      setState(() {
        final index = _messages.indexWhere((m) => m.id == pendingId);
        final transcriptMessage = Message(
          id: _uuid.v4(),
          role: MessageRole.user,
          content: response.transcript,
          createdAt: DateTime.now(),
          isVoiceInput: true,
        );
        final answerMessage = Message(
          id: response.requestId,
          role: MessageRole.assistant,
          content: response.answer,
          createdAt: DateTime.now(),
          sourceQuery: response.transcript,
          metadata: response.reasoning != null
              ? {'reasoning': response.reasoning}
              : const {},
        );
        if (index != -1) {
          _messages.removeAt(index);
          _messages.add(transcriptMessage);
          _messages.add(answerMessage);
        }
      });

      if (widget.preferences.autoPlayResponses && response.audio != null) {
        _playServerAudio(response.audio!.url);
      }
    } on ApiException catch (e) {
      // STT can succeed (and get persisted server-side) even when the
      // agent step fails afterward -- see gateway/API.md's "transcript"
      // sibling field. Without this, whatever the user said would vanish
      // behind a bare error instead of showing up in the conversation.
      final transcript = e.transcript;
      if (transcript != null && transcript.isNotEmpty) {
        setState(() {
          final index = _messages.indexWhere((m) => m.id == pendingId);
          final transcriptMessage = Message(
            id: _uuid.v4(),
            role: MessageRole.user,
            content: transcript,
            createdAt: DateTime.now(),
            isVoiceInput: true,
          );
          final errorMessage = Message(
            id: pendingId,
            role: MessageRole.assistant,
            content: userMessageFor(e),
            createdAt: DateTime.now(),
            isError: true,
            sourceQuery: transcript,
          );
          if (index != -1) {
            _messages[index] = errorMessage;
            _messages.insert(index, transcriptMessage);
          } else {
            _messages.addAll([transcriptMessage, errorMessage]);
          }
        });
        if (e.code == ApiErrorCode.unauthorized) _routeToServerSetup();
      } else {
        _handleError(e, pendingId, '');
      }
    } catch (_) {
      _replacePending(
        pendingId,
        Message(
          id: pendingId,
          role: MessageRole.assistant,
          content: 'Something went wrong processing your recording.',
          createdAt: DateTime.now(),
          isError: true,
        ),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToBottom();
      await _recorder.deleteRecording(path);
    }
  }

  void _send() {
    final text = _textController.text;
    _textController.clear();
    _sendQuery(text);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Plane Assistant'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'New conversation',
            onPressed: _newConversation,
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => SettingsScreen(
                    preferences: widget.preferences,
                    secureStorage: widget.secureStorage,
                  ),
                ),
              );
              _initClient();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: _messages.isEmpty
                ? Center(
                    child: Text(
                      'Ask me anything about your Plane workspace.',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final message = _messages[index];
                      return MessageBubble(
                        message: message,
                        isSpeaking: _speakingMessageId == message.id,
                        onCopy: message.role == MessageRole.assistant
                            ? () => _copy(message)
                            : null,
                        onSpeak: message.role == MessageRole.assistant
                            ? () => _speak(message)
                            : null,
                        onRetry: message.role == MessageRole.assistant &&
                                message.sourceQuery != null
                            ? () => _retry(message)
                            : null,
                      );
                    },
                  ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  IconButton(
                    key: const Key('mic_button'),
                    icon: const Icon(Icons.mic),
                    tooltip: 'Record voice query',
                    onPressed: _sending ? null : _startRecording,
                  ),
                  Expanded(
                    child: TextField(
                      key: const Key('query_text_field'),
                      controller: _textController,
                      decoration: const InputDecoration(
                        hintText: 'Ask about your Plane workspace...',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      onSubmitted: (_) => _sending ? null : _send(),
                      textInputAction: TextInputAction.send,
                    ),
                  ),
                  IconButton(
                    key: const Key('send_button'),
                    icon: const Icon(Icons.send),
                    tooltip: 'Send',
                    onPressed: _sending ? null : _send,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
