import 'dart:io';

import 'package:flutter/services.dart';

/// Bridges to MainActivity.kt's platform channel for the home-screen
/// widget: things only a real Activity context can do (request the "draw
/// over other apps" permission, ask the launcher to pin the widget) that
/// neither Dart nor the widget's own background service can do alone.
/// No-ops on non-Android platforms.
class WidgetSetup {
  static const _channel = MethodChannel('com.planeassistant.plane_assistant/widget_setup');

  Future<bool> hasOverlayPermission() async {
    if (!Platform.isAndroid) return false;
    final result = await _channel.invokeMethod<bool>('hasOverlayPermission');
    return result ?? false;
  }

  Future<void> openOverlayPermissionSettings() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<void>('openOverlayPermissionSettings');
  }

  /// Asks the launcher to show its "add this widget to your home screen"
  /// confirmation. Returns false if the launcher doesn't support the
  /// request (Android < 8, or a launcher that never implemented it) --
  /// callers should fall back to telling the user to add it manually via
  /// their launcher's widget picker.
  Future<bool> requestPinWidget() async {
    if (!Platform.isAndroid) return false;
    final result = await _channel.invokeMethod<bool>('requestPinWidget');
    return result ?? false;
  }
}
