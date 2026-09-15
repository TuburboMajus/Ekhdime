import 'package:flutter/material.dart';

/// A simple dropdown for choosing a TTS voice, populated from
/// `GET /api/v1/tts/voices`. Degrades gracefully to a disabled placeholder
/// when [voices] is empty (e.g. the endpoint failed).
class VoicePicker extends StatelessWidget {
  final List<String> voices;
  final String? selected;
  final ValueChanged<String?> onChanged;
  final bool loading;

  const VoicePicker({
    super.key,
    required this.voices,
    required this.selected,
    required this.onChanged,
    this.loading = false,
  });

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const ListTile(
        title: Text('Voice'),
        trailing: SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }

    if (voices.isEmpty) {
      return const ListTile(
        title: Text('Voice'),
        subtitle: Text('Unavailable -- using server default'),
        enabled: false,
      );
    }

    final value = voices.contains(selected) ? selected : null;

    return ListTile(
      title: const Text('Voice'),
      trailing: DropdownButton<String>(
        value: value,
        hint: const Text('Default'),
        items: voices
            .map((v) => DropdownMenuItem(value: v, child: Text(v)))
            .toList(),
        onChanged: onChanged,
      ),
    );
  }
}
