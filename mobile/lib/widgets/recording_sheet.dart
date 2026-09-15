import 'dart:async';

import 'package:flutter/material.dart';

import '../services/audio_player_service.dart';
import '../services/audio_recorder_service.dart';

enum _RecordingStage { recording, preview }

/// Result returned when the recording sheet is dismissed after the user
/// taps Send: the path to the recorded audio file.
class RecordingResult {
  final String path;
  const RecordingResult(this.path);
}

/// Bottom sheet driving the record -> preview -> send flow: tap mic already
/// started recording by the time this is shown; shows an elapsed timer,
/// then on stop offers Play/Re-record/Delete/Send.
///
/// Caller is responsible for requesting RECORD_AUDIO permission before
/// showing this sheet.
class RecordingSheet extends StatefulWidget {
  final AudioRecorderService recorder;
  final AudioPlayerService player;

  const RecordingSheet({
    super.key,
    required this.recorder,
    required this.player,
  });

  static Future<RecordingResult?> show(
    BuildContext context, {
    required AudioRecorderService recorder,
    required AudioPlayerService player,
  }) {
    return showModalBottomSheet<RecordingResult>(
      context: context,
      isDismissible: false,
      enableDrag: false,
      builder: (_) => RecordingSheet(recorder: recorder, player: player),
    );
  }

  @override
  State<RecordingSheet> createState() => _RecordingSheetState();
}

class _RecordingSheetState extends State<RecordingSheet> {
  _RecordingStage _stage = _RecordingStage.recording;
  Duration _elapsed = Duration.zero;
  String? _recordedPath;
  StreamSubscription<Duration>? _elapsedSub;
  bool _isPlaying = false;
  StreamSubscription? _playerStateSub;

  @override
  void initState() {
    super.initState();
    _elapsedSub = widget.recorder.elapsed.listen((d) {
      if (mounted) setState(() => _elapsed = d);
    });
    _startIfNeeded();
  }

  Future<void> _startIfNeeded() async {
    if (!widget.recorder.isRecording) {
      await widget.recorder.start();
      if (mounted) setState(() {});
    }
  }

  Future<void> _stop() async {
    final path = await widget.recorder.stop();
    if (!mounted) return;
    setState(() {
      _recordedPath = path;
      _stage = _RecordingStage.preview;
    });
  }

  Future<void> _rerecord() async {
    if (_recordedPath != null) {
      await widget.recorder.deleteRecording(_recordedPath!);
    }
    setState(() {
      _recordedPath = null;
      _elapsed = Duration.zero;
      _stage = _RecordingStage.recording;
    });
    await widget.recorder.start();
  }

  Future<void> _delete() async {
    if (_recordedPath != null) {
      await widget.recorder.deleteRecording(_recordedPath!);
    }
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _playPreview() async {
    if (_recordedPath == null) return;
    if (_isPlaying) {
      await widget.player.stop();
      setState(() => _isPlaying = false);
      return;
    }
    setState(() => _isPlaying = true);
    await widget.player.playFile(_recordedPath!);
    _playerStateSub?.cancel();
    _playerStateSub = widget.player.playerStateStream.listen((state) {
      if (state.processingState.toString().contains('completed') && mounted) {
        setState(() => _isPlaying = false);
      }
    });
  }

  void _send() {
    if (_recordedPath == null) return;
    Navigator.of(context).pop(RecordingResult(_recordedPath!));
  }

  Future<void> _cancel() async {
    if (_stage == _RecordingStage.recording) {
      await widget.recorder.cancel();
    } else if (_recordedPath != null) {
      await widget.recorder.deleteRecording(_recordedPath!);
    }
    if (mounted) Navigator.of(context).pop();
  }

  String _formatDuration(Duration d) {
    final minutes = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  void dispose() {
    _elapsedSub?.cancel();
    _playerStateSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _stage == _RecordingStage.recording ? 'Recording...' : 'Preview',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            Text(
              _formatDuration(_elapsed),
              style: Theme.of(context).textTheme.displaySmall,
            ),
            const SizedBox(height: 24),
            if (_stage == _RecordingStage.recording)
              _RecordingControls(onStop: _stop, onCancel: _cancel)
            else
              _PreviewControls(
                isPlaying: _isPlaying,
                onPlay: _playPreview,
                onRerecord: _rerecord,
                onDelete: _delete,
                onSend: _send,
              ),
          ],
        ),
      ),
    );
  }
}

class _RecordingControls extends StatelessWidget {
  final VoidCallback onStop;
  final VoidCallback onCancel;

  const _RecordingControls({required this.onStop, required this.onCancel});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        TextButton(onPressed: onCancel, child: const Text('Cancel')),
        const SizedBox(width: 24),
        FloatingActionButton(
          onPressed: onStop,
          backgroundColor: Colors.red,
          child: const Icon(Icons.stop, color: Colors.white),
        ),
      ],
    );
  }
}

class _PreviewControls extends StatelessWidget {
  final bool isPlaying;
  final VoidCallback onPlay;
  final VoidCallback onRerecord;
  final VoidCallback onDelete;
  final VoidCallback onSend;

  const _PreviewControls({
    required this.isPlaying,
    required this.onPlay,
    required this.onRerecord,
    required this.onDelete,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _LabeledIconButton(
              icon: isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill,
              label: isPlaying ? 'Pause' : 'Play',
              onPressed: onPlay,
            ),
            _LabeledIconButton(
              icon: Icons.mic,
              label: 'Re-record',
              onPressed: onRerecord,
            ),
            _LabeledIconButton(
              icon: Icons.delete_outline,
              label: 'Delete',
              onPressed: onDelete,
            ),
          ],
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: onSend,
          icon: const Icon(Icons.send),
          label: const Text('Send'),
        ),
      ],
    );
  }
}

class _LabeledIconButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  const _LabeledIconButton({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          iconSize: 36,
          icon: Icon(icon),
          onPressed: onPressed,
        ),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
