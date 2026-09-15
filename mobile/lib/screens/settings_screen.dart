import 'package:flutter/material.dart';

import 'dart:io';

import '../api/api_client.dart';
import '../api/connection_test.dart';
import '../api/server_url.dart';
import '../models/health.dart';
import '../services/widget_setup.dart';
import '../storage/app_preferences.dart';
import '../storage/secure_storage.dart';
import '../widgets/voice_picker.dart';

class SettingsScreen extends StatefulWidget {
  final AppPreferences preferences;
  final SecureStorage secureStorage;

  const SettingsScreen({
    super.key,
    required this.preferences,
    required this.secureStorage,
  });

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> with WidgetsBindingObserver {
  final _urlController = TextEditingController();
  final _tokenController = TextEditingController();
  final _widgetSetup = WidgetSetup();

  bool _autoPlay = false;
  double _speed = 1.0;
  String? _voice;
  String? _language;
  bool _showTranscript = false;
  bool _hasOverlayPermission = false;

  List<String> _voices = [];
  bool _loadingVoices = false;
  String? _connectionStatusText;
  Color? _connectionStatusColor;
  bool _testingConnection = false;
  ServerInfo? _serverInfo;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _urlController.text = widget.preferences.serverUrl ?? '';
    _autoPlay = widget.preferences.autoPlayResponses;
    _speed = widget.preferences.ttsSpeed;
    _voice = widget.preferences.ttsVoice;
    _language = widget.preferences.inputLanguage;
    _showTranscript = widget.preferences.showTranscriptBeforeProcessing;
    _loadToken();
    _loadVoices();
    _loadServerInfo();
    _loadOverlayPermission();
  }

  Future<void> _loadOverlayPermission() async {
    final granted = await _widgetSetup.hasOverlayPermission();
    if (mounted) setState(() => _hasOverlayPermission = granted);
  }

  Future<void> _loadToken() async {
    final token = await widget.secureStorage.readToken();
    if (mounted && token != null) {
      _tokenController.text = token;
    }
  }

  Future<void> _loadVoices() async {
    final baseUrl = widget.preferences.serverUrl;
    if (baseUrl == null) return;
    setState(() => _loadingVoices = true);
    try {
      final token = await widget.secureStorage.readToken();
      final client = ApiClient(baseUrl: baseUrl, token: token);
      try {
        final result = await client.ttsVoices();
        if (mounted) {
          setState(() {
            _voices = result.voices;
            _voice ??= result.defaultVoice;
          });
        }
      } finally {
        client.close();
      }
    } catch (_) {
      // Degrade gracefully: leave the voice list empty.
    } finally {
      if (mounted) setState(() => _loadingVoices = false);
    }
  }

  Future<void> _loadServerInfo() async {
    final baseUrl = widget.preferences.serverUrl;
    if (baseUrl == null) return;
    try {
      final client = ApiClient(baseUrl: baseUrl);
      try {
        final info = await client.info();
        if (mounted) setState(() => _serverInfo = info);
      } finally {
        client.close();
      }
    } catch (_) {
      // About section just won't show version info.
    }
  }

  Future<void> _testConnection() async {
    setState(() {
      _testingConnection = true;
      _connectionStatusText = null;
    });
    String normalized;
    try {
      normalized = ServerUrl.normalize(_urlController.text);
    } on FormatException catch (e) {
      setState(() {
        _testingConnection = false;
        _connectionStatusText = e.message;
        _connectionStatusColor = Colors.red;
      });
      return;
    }

    final result = await testConnection(
      baseUrl: normalized,
      token: _tokenController.text.trim(),
    );
    if (!mounted) return;
    setState(() {
      _testingConnection = false;
      switch (result.status) {
        case ConnectionStatus.connected:
          _connectionStatusText = 'Connected';
          _connectionStatusColor = Colors.green;
          break;
        case ConnectionStatus.authenticationFailed:
          _connectionStatusText = 'Authentication failed -- check your API token.';
          _connectionStatusColor = Colors.orange;
          break;
        case ConnectionStatus.unreachable:
          _connectionStatusText = 'Server unreachable.';
          _connectionStatusColor = Colors.red;
          break;
      }
    });
  }

  Future<void> _saveServerConfig() async {
    try {
      final normalized = ServerUrl.normalize(_urlController.text);
      await widget.preferences.setServerUrl(normalized);
      final token = _tokenController.text.trim();
      await widget.secureStorage.writeToken(token);
      await widget.preferences.setWidgetToken(token);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Server settings saved.')));
      }
      _loadVoices();
      _loadServerInfo();
    } on FormatException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The overlay permission is granted from a system Settings screen this
    // screen navigates away to -- re-check whenever the app comes back to
    // the foreground rather than only once in initState.
    if (state == AppLifecycleState.resumed) _loadOverlayPermission();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _urlController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          const _SectionHeader('Server'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              controller: _urlController,
              decoration: const InputDecoration(labelText: 'Server URL'),
              keyboardType: TextInputType.url,
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              controller: _tokenController,
              decoration: const InputDecoration(labelText: 'API Token'),
              obscureText: true,
            ),
          ),
          if (_connectionStatusText != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text(
                _connectionStatusText!,
                style: TextStyle(color: _connectionStatusColor),
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _testingConnection ? null : _testConnection,
                    child: _testingConnection
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Test Connection'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: _saveServerConfig,
                    child: const Text('Save'),
                  ),
                ),
              ],
            ),
          ),
          const Divider(),
          const _SectionHeader('Voice & Playback'),
          SwitchListTile(
            title: const Text('Auto-play responses'),
            subtitle: const Text('Automatically speak assistant answers'),
            value: _autoPlay,
            onChanged: (value) {
              setState(() => _autoPlay = value);
              widget.preferences.setAutoPlayResponses(value);
            },
          ),
          VoicePicker(
            voices: _voices,
            selected: _voice,
            loading: _loadingVoices,
            onChanged: (value) {
              setState(() => _voice = value);
              widget.preferences.setTtsVoice(value);
            },
          ),
          ListTile(
            title: const Text('Playback speed'),
            subtitle: Slider(
              value: _speed,
              min: 0.5,
              max: 2.0,
              divisions: 6,
              label: '${_speed.toStringAsFixed(2)}x',
              onChanged: (value) {
                setState(() => _speed = value);
              },
              onChangeEnd: (value) {
                widget.preferences.setTtsSpeed(value);
              },
            ),
          ),
          const Divider(),
          const _SectionHeader('Voice Input'),
          ListTile(
            title: const Text('Preferred input language'),
            subtitle: Text(_language ?? 'Auto-detect'),
            trailing: DropdownButton<String?>(
              value: _language,
              hint: const Text('Auto'),
              items: const [
                DropdownMenuItem(value: null, child: Text('Auto-detect')),
                DropdownMenuItem(value: 'en', child: Text('English')),
                DropdownMenuItem(value: 'fr', child: Text('French')),
                DropdownMenuItem(value: 'es', child: Text('Spanish')),
                DropdownMenuItem(value: 'de', child: Text('German')),
                DropdownMenuItem(value: 'ar', child: Text('Arabic')),
              ],
              onChanged: (value) {
                setState(() => _language = value);
                widget.preferences.setInputLanguage(value);
              },
            ),
          ),
          SwitchListTile(
            title: const Text('Show transcription before processing'),
            subtitle: const Text(
              'Review and edit your voice query before it is sent',
            ),
            value: _showTranscript,
            onChanged: (value) {
              setState(() => _showTranscript = value);
              widget.preferences.setShowTranscriptBeforeProcessing(value);
            },
          ),
          if (Platform.isAndroid) ...[
            const Divider(),
            const _SectionHeader('Home-Screen Widget'),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'Add the widget to your home screen to talk to the assistant '
                'in one tap, without opening the app. Save your server and '
                'token above first.',
              ),
            ),
            ListTile(
              title: const Text('"Draw over other apps" permission'),
              subtitle: Text(
                _hasOverlayPermission
                    ? 'Granted -- the widget will show a listening indicator.'
                    : 'Not granted -- the widget still works, but without a '
                        'visible indicator while it listens.',
              ),
              trailing: _hasOverlayPermission
                  ? const Icon(Icons.check_circle, color: Colors.green)
                  : OutlinedButton(
                      onPressed: () => _widgetSetup.openOverlayPermissionSettings(),
                      child: const Text('Grant'),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: OutlinedButton(
                onPressed: () async {
                  final pinned = await _widgetSetup.requestPinWidget();
                  if (!context.mounted) return;
                  if (!pinned) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text(
                          "Couldn't request pinning automatically -- add "
                          '"Plane Assistant" from your launcher\'s widget '
                          'picker instead.',
                        ),
                      ),
                    );
                  }
                },
                child: const Text('Add widget to home screen'),
              ),
            ),
          ],
          const Divider(),
          const _SectionHeader('About'),
          ListTile(
            title: const Text('App version'),
            subtitle: const Text('1.0.0'),
          ),
          ListTile(
            title: const Text('Server version'),
            subtitle: Text(_serverInfo?.serverVersion ?? 'Unknown'),
          ),
          ListTile(
            title: const Text('API version'),
            subtitle: Text(_serverInfo?.apiVersion ?? 'Unknown'),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(
        title,
        style: Theme.of(context)
            .textTheme
            .titleSmall
            ?.copyWith(color: Theme.of(context).colorScheme.primary),
      ),
    );
  }
}
