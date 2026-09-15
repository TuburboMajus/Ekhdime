package com.planeassistant.plane_assistant

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import androidx.core.content.ContextCompat

/**
 * The home-screen widget itself: a single circular button, like the
 * Shazam/Google-search widgets it mirrors. A tap never opens the app UI --
 * it starts [VoiceRecordingService] directly, which records, calls the
 * gateway, and speaks the answer back via a floating overlay.
 *
 * Starting a foreground service from a plain widget tap is restricted on
 * Android 12+ background-start rules; routing the tap through this
 * receiver's own `onReceive` (widgets are AppWidgetProviders, which *are*
 * BroadcastReceivers) is the documented exemption -- a PendingIntent
 * targeting a Service directly would not get it.
 */
class VoiceWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray,
    ) {
        for (widgetId in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.voice_widget)
            val tapIntent = Intent(context, VoiceWidgetProvider::class.java).apply {
                action = ACTION_START_LISTENING
            }
            val pendingIntent = PendingIntent.getBroadcast(
                context,
                widgetId,
                tapIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            views.setOnClickPendingIntent(R.id.voice_widget_button, pendingIntent)
            appWidgetManager.updateAppWidget(widgetId, views)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_START_LISTENING) {
            val serviceIntent = Intent(context, VoiceRecordingService::class.java)
            ContextCompat.startForegroundService(context, serviceIntent)
        }
    }

    companion object {
        const val ACTION_START_LISTENING =
            "com.planeassistant.plane_assistant.action.START_LISTENING"
    }
}
