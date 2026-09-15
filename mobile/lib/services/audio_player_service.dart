import 'dart:io';
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';

/// Wraps `just_audio` for the two playback needs in this app: replaying a
/// locally recorded clip (preview before sending) and playing back
/// server-synthesized TTS audio bytes.
class AudioPlayerService {
  final AudioPlayer _player;

  AudioPlayerService({AudioPlayer? player}) : _player = player ?? AudioPlayer();

  Stream<PlayerState> get playerStateStream => _player.playerStateStream;
  Stream<Duration> get positionStream => _player.positionStream;
  Duration? get duration => _player.duration;
  bool get isPlaying => _player.playing;

  /// Plays a local file at [path] (e.g. a just-recorded preview clip).
  Future<void> playFile(String path) async {
    await _player.setFilePath(path);
    await _player.play();
  }

  /// Plays raw audio bytes (e.g. a `/tts` response) by writing them to a
  /// temp file first, since `just_audio` needs a source URI.
  Future<void> playBytes(Uint8List bytes, {String extension = 'mp3'}) async {
    final dir = await getTemporaryDirectory();
    final file = File(
      '${dir.path}/plane_assistant_tts_${DateTime.now().millisecondsSinceEpoch}.$extension',
    );
    await file.writeAsBytes(bytes, flush: true);
    await _player.setFilePath(file.path);
    await _player.play();
  }

  /// Plays audio from a remote URL directly (used when the caller already
  /// has an authenticated, resolvable URL -- otherwise prefer fetching
  /// bytes via [ApiClient.audioResponse] and calling [playBytes]).
  Future<void> playUrl(String url) async {
    await _player.setUrl(url);
    await _player.play();
  }

  Future<void> pause() => _player.pause();

  Future<void> resume() => _player.play();

  Future<void> stop() => _player.stop();

  Future<void> setSpeed(double speed) => _player.setSpeed(speed);

  void dispose() {
    _player.dispose();
  }
}
