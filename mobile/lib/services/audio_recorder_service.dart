import 'dart:async';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Wraps the `record` package to capture microphone audio to a temp file,
/// exposing a simple start/stop/duration API plus a live elapsed-time
/// stream for the recording UI.
class AudioRecorderService {
  final AudioRecorder _recorder;
  StreamController<Duration>? _elapsedController;
  Timer? _ticker;
  DateTime? _startedAt;
  String? _currentPath;

  AudioRecorderService({AudioRecorder? recorder})
      : _recorder = recorder ?? AudioRecorder();

  /// Emits the elapsed recording duration roughly once per 100ms while
  /// recording is in progress.
  Stream<Duration> get elapsed =>
      (_elapsedController ??= StreamController<Duration>.broadcast()).stream;

  bool get isRecording => _startedAt != null;

  /// Whether the OS-level permission for microphone capture is granted.
  /// Prefer checking via `permission_handler` in the UI layer for the
  /// user-facing flow; this is a convenience passthrough for the recorder
  /// itself.
  Future<bool> hasPermission() => _recorder.hasPermission();

  /// Starts recording to a new temp file. Throws a [StateError] if a
  /// recording is already in progress.
  Future<void> start() async {
    if (isRecording) {
      throw StateError('A recording is already in progress.');
    }
    final dir = await getTemporaryDirectory();
    final path =
        '${dir.path}/plane_assistant_recording_${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc),
      path: path,
    );
    _currentPath = path;
    _startedAt = DateTime.now();
    _elapsedController ??= StreamController<Duration>.broadcast();
    _ticker = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (_startedAt != null) {
        _elapsedController?.add(DateTime.now().difference(_startedAt!));
      }
    });
  }

  /// Stops recording and returns the path to the recorded file, or null if
  /// nothing was recorded.
  Future<String?> stop() async {
    _ticker?.cancel();
    _ticker = null;
    _startedAt = null;
    final path = await _recorder.stop();
    return path ?? _currentPath;
  }

  /// Cancels the current recording and deletes the partial file.
  Future<void> cancel() async {
    _ticker?.cancel();
    _ticker = null;
    _startedAt = null;
    try {
      await _recorder.cancel();
    } catch (_) {
      // Best-effort: some platforms throw if nothing is recording.
    }
    final path = _currentPath;
    _currentPath = null;
    if (path != null) {
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
      }
    }
  }

  /// Deletes a previously recorded file (e.g. after the user chooses
  /// "Delete" in the preview step).
  Future<void> deleteRecording(String path) async {
    final file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
  }

  void dispose() {
    _ticker?.cancel();
    _elapsedController?.close();
    _recorder.dispose();
  }
}
