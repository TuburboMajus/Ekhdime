package com.planeassistant.plane_assistant

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Everything the home-screen widget needs from a real Activity context --
 * requesting the "draw over other apps" permission and asking the launcher
 * to pin the widget -- neither of which [VoiceRecordingService] (no
 * Activity, often no visible UI at all) can do for itself. See
 * mobile/lib/services/widget_setup.dart for the Dart side of this channel.
 */
class MainActivity : FlutterActivity() {
    private val channelName = "com.planeassistant.plane_assistant/widget_setup"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "hasOverlayPermission" -> result.success(Settings.canDrawOverlays(this))
                    "openOverlayPermissionSettings" -> {
                        startActivity(
                            Intent(
                                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                Uri.parse("package:$packageName"),
                            ),
                        )
                        result.success(null)
                    }
                    "requestPinWidget" -> result.success(requestPinWidget())
                    else -> result.notImplemented()
                }
            }
    }

    private fun requestPinWidget(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return false
        val appWidgetManager = getSystemService(AppWidgetManager::class.java) ?: return false
        val provider = ComponentName(this, VoiceWidgetProvider::class.java)
        if (!appWidgetManager.isRequestPinAppWidgetSupported) return false
        return appWidgetManager.requestPinAppWidget(provider, null, null)
    }
}
