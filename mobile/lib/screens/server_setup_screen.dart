import 'package:flutter/material.dart';

import '../api/connection_test.dart';
import '../api/server_url.dart';
import '../storage/app_preferences.dart';
import '../storage/secure_storage.dart';
import 'conversation_screen.dart';

/// First-launch (and re-auth) screen: collects the gateway server URL and
/// API token, validates/tests them, and persists on success.
class ServerSetupScreen extends StatefulWidget {
  final AppPreferences preferences;
  final SecureStorage secureStorage;

  const ServerSetupScreen({
    super.key,
    required this.preferences,
    required this.secureStorage,
  });

  @override
  State<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

enum _TestState { idle, testing, connected, authFailed, unreachable, invalidUrl }

class _ServerSetupScreenState extends State<ServerSetupScreen> {
  final _urlController = TextEditingController();
  final _tokenController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  _TestState _state = _TestState.idle;
  String? _errorDetail;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    // Falls back to a build-time default (--dart-define=DEFAULT_SERVER_URL=...,
    // see ../../Dockerfile) only when nothing has been saved yet -- a saved
    // preference always wins.
    _urlController.text = widget.preferences.serverUrl ??
        const String.fromEnvironment('DEFAULT_SERVER_URL');
  }

  @override
  void dispose() {
    _urlController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  String? _validateUrl(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Server URL is required.';
    }
    try {
      ServerUrl.normalize(value);
      return null;
    } on FormatException catch (e) {
      return e.message;
    }
  }

  Future<void> _testConnection() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      setState(() => _state = _TestState.invalidUrl);
      return;
    }

    final String normalized;
    try {
      normalized = ServerUrl.normalize(_urlController.text);
    } on FormatException {
      setState(() => _state = _TestState.invalidUrl);
      return;
    }

    setState(() {
      _state = _TestState.testing;
      _errorDetail = null;
    });

    final result = await testConnection(
      baseUrl: normalized,
      token: _tokenController.text.trim(),
    );

    if (!mounted) return;
    setState(() {
      _errorDetail = result.detail;
      switch (result.status) {
        case ConnectionStatus.connected:
          _state = _TestState.connected;
          break;
        case ConnectionStatus.authenticationFailed:
          _state = _TestState.authFailed;
          break;
        case ConnectionStatus.unreachable:
          _state = _TestState.unreachable;
          break;
      }
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final normalized = ServerUrl.normalize(_urlController.text);
    final token = _tokenController.text.trim();

    setState(() => _saving = true);
    await widget.preferences.setServerUrl(normalized);
    await widget.secureStorage.writeToken(token);
    await widget.preferences.setWidgetToken(token);
    setState(() => _saving = false);

    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => ConversationScreen(
          preferences: widget.preferences,
          secureStorage: widget.secureStorage,
        ),
      ),
    );
  }

  Widget _statusBanner() {
    switch (_state) {
      case _TestState.idle:
        return const SizedBox.shrink();
      case _TestState.testing:
        return const _StatusRow(
          icon: Icons.hourglass_top,
          color: Colors.grey,
          text: 'Testing connection...',
        );
      case _TestState.connected:
        return const _StatusRow(
          icon: Icons.check_circle,
          color: Colors.green,
          text: 'Connected',
        );
      case _TestState.authFailed:
        return const _StatusRow(
          icon: Icons.lock_outline,
          color: Colors.orange,
          text: 'Authentication failed -- check your API token.',
        );
      case _TestState.unreachable:
        return _StatusRow(
          icon: Icons.cloud_off,
          color: Colors.red,
          text: _errorDetail == null
              ? 'Server unreachable. Check the URL and your network.'
              : 'Server unreachable: $_errorDetail',
        );
      case _TestState.invalidUrl:
        return const _StatusRow(
          icon: Icons.error_outline,
          color: Colors.red,
          text: 'Please enter a valid server URL.',
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Connect to your Plane gateway')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Plane Assistant',
                  style: Theme.of(context).textTheme.headlineSmall,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Enter the address of your self-hosted gateway and your API token to get started.',
                  style: Theme.of(context).textTheme.bodyMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                TextFormField(
                  key: const Key('server_url_field'),
                  controller: _urlController,
                  decoration: const InputDecoration(
                    labelText: 'Server URL',
                    hintText: 'http://10.0.2.2:8088',
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  validator: _validateUrl,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('api_token_field'),
                  controller: _tokenController,
                  decoration: const InputDecoration(
                    labelText: 'API Token',
                    border: OutlineInputBorder(),
                  ),
                  obscureText: true,
                  autocorrect: false,
                ),
                const SizedBox(height: 16),
                _statusBanner(),
                const SizedBox(height: 16),
                OutlinedButton(
                  key: const Key('test_connection_button'),
                  onPressed: _state == _TestState.testing ? null : _testConnection,
                  child: const Text('Test Connection'),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  key: const Key('save_button'),
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String text;

  const _StatusRow({required this.icon, required this.color, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: color),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: TextStyle(color: color))),
      ],
    );
  }
}
