package com.planeassistant.plane_assistant

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.PixelFormat
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Records from the mic, calls the gateway's `/query/audio`, and speaks the
 * answer back -- all without ever opening [MainActivity]. Started only by
 * [VoiceWidgetProvider] in response to a home-screen widget tap.
 *
 * Networking reads the server URL and a plaintext-mirrored copy of the
 * bearer token directly out of the same SharedPreferences file the Flutter
 * `shared_preferences` plugin writes (see AppPreferences.setWidgetToken and
 * SecureStorage's docstring for why a mirror exists at all -- this service
 * has no running Flutter engine to ask, and re-implementing
 * flutter_secure_storage's Keystore-backed encryption in Kotlin to read its
 * store directly would be far more fragile than one deliberate,
 * documented exception).
 */
class VoiceRecordingService : Service() {

    private var windowManager: WindowManager? = null
    private var overlayView: View? = null
    private var recorder: MediaRecorder? = null
    private var mediaPlayer: MediaPlayer? = null
    private var recordingFile: File? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var stopRecordingRunnable: Runnable? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(REQUEST_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .writeTimeout(REQUEST_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .build()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification(getString(R.string.voice_notification_listening)))

        if (!startRecording()) {
            finishAndCleanup()
            return START_NOT_STICKY
        }
        showOverlay()

        val runnable = Runnable { stopRecordingAndSend() }
        stopRecordingRunnable = runnable
        mainHandler.postDelayed(runnable, MAX_RECORDING_MS)
        return START_NOT_STICKY
    }

    // --- Notification ------------------------------------------------------

    private fun buildNotification(text: String): Notification {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            if (manager.getNotificationChannel(CHANNEL_ID) == null) {
                manager.createNotificationChannel(
                    NotificationChannel(
                        CHANNEL_ID,
                        getString(R.string.voice_notification_channel_name),
                        NotificationManager.IMPORTANCE_LOW,
                    ),
                )
            }
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.voice_widget_description))
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_mic_notification)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    // --- Floating overlay ---------------------------------------------------

    private fun showOverlay() {
        // Degrade gracefully rather than refuse to work: recording and the
        // gateway round-trip still happen and the answer is still spoken,
        // just without a visible "listening/thinking" bubble, if the user
        // hasn't granted "draw over other apps" yet.
        if (!Settings.canDrawOverlays(this)) return

        val view = LayoutInflater.from(this).inflate(R.layout.voice_overlay, null)
        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        )
        params.gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
        params.y = 120

        view.findViewById<View>(R.id.overlay_bubble).setOnClickListener { stopRecordingAndSend() }

        val manager = getSystemService(WINDOW_SERVICE) as WindowManager
        try {
            manager.addView(view, params)
            windowManager = manager
            overlayView = view
        } catch (e: Exception) {
            // Some OEM overlay implementations reject addView() even when
            // canDrawOverlays() reports true; never let that take the whole
            // recording flow down with it.
            windowManager = null
            overlayView = null
        }
    }

    private fun setOverlayState(thinking: Boolean) {
        val view = overlayView ?: return
        view.findViewById<TextView>(R.id.overlay_status).setText(
            if (thinking) R.string.voice_notification_thinking else R.string.voice_notification_listening,
        )
    }

    private fun removeOverlay() {
        val view = overlayView ?: return
        try {
            windowManager?.removeView(view)
        } catch (_: Exception) {
            // Already removed, or the window manager never actually
            // accepted it in showOverlay() -- either way, nothing to clean
            // up.
        }
        overlayView = null
    }

    // --- Recording -----------------------------------------------------------

    private fun startRecording(): Boolean {
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            toast("Microphone permission not granted. Open Plane Assistant once to grant it.")
            return false
        }
        return try {
            val file = File(cacheDir, "widget_recording_${System.currentTimeMillis()}.m4a")
            val mr = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(this)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }
            mr.setAudioSource(MediaRecorder.AudioSource.MIC)
            mr.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            mr.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            mr.setOutputFile(file.absolutePath)
            mr.prepare()
            mr.start()
            recorder = mr
            recordingFile = file
            true
        } catch (e: IOException) {
            toast("Could not start recording: ${e.message}")
            false
        } catch (e: IllegalStateException) {
            toast("Could not start recording: ${e.message}")
            false
        }
    }

    private fun stopRecordingAndSend() {
        stopRecordingRunnable?.let { mainHandler.removeCallbacks(it) }
        stopRecordingRunnable = null

        val file = recordingFile
        try {
            recorder?.stop()
        } catch (_: Exception) {
            // stop() throws if called within ~milliseconds of start(); the
            // file on disk is just whatever MediaRecorder had flushed,
            // which the "empty/missing file" check below already handles.
        }
        recorder?.release()
        recorder = null

        if (file == null || !file.exists() || file.length() == 0L) {
            toast("No audio recorded.")
            finishAndCleanup()
            return
        }

        setOverlayState(thinking = true)
        updateNotification(getString(R.string.voice_notification_thinking))
        sendToGateway(file)
    }

    // --- Gateway networking -----------------------------------------------

    private fun sendToGateway(file: File) {
        val prefs = getSharedPreferences(FLUTTER_PREFS_NAME, MODE_PRIVATE)
        val serverUrl = prefs.getString(SERVER_URL_PREF_KEY, null)?.trimEnd('/')
        val token = prefs.getString(WIDGET_TOKEN_PREF_KEY, null)
        val language = prefs.getString(INPUT_LANGUAGE_PREF_KEY, null)

        if (serverUrl.isNullOrBlank() || token.isNullOrBlank()) {
            file.delete()
            toast("Open Plane Assistant once and sign in before using the widget.")
            finishAndCleanup()
            return
        }

        val bodyBuilder = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", file.name, file.asRequestBody("audio/mp4".toMediaType()))
            .addFormDataPart("include_audio", "true")
        if (!language.isNullOrBlank()) {
            bodyBuilder.addFormDataPart("language", language)
        }

        val request = Request.Builder()
            .url("$serverUrl/api/v1/query/audio")
            .header("Authorization", "Bearer $token")
            .post(bodyBuilder.build())
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                file.delete()
                toast("Network error: ${e.message}")
                finishAndCleanup()
            }

            override fun onResponse(call: Call, response: Response) {
                file.delete()
                response.use { resp ->
                    val bodyText = resp.body?.string().orEmpty()
                    val json = try {
                        JSONObject(bodyText)
                    } catch (e: Exception) {
                        null
                    }

                    if (!resp.isSuccessful) {
                        val code = json?.optJSONObject("error")?.optString("code").orEmpty()
                        toast(friendlyMessageFor(code, resp.code))
                        finishAndCleanup()
                        return
                    }

                    val audio = json?.optJSONObject("audio")
                    val audioUrl = audio?.optString("url")?.takeIf {
                        it.isNotBlank() && audio.optBoolean("available")
                    }
                    if (audioUrl != null) {
                        playAnswerAudio(serverUrl, token, audioUrl)
                    } else {
                        val answer = json?.optString("answer")
                        if (!answer.isNullOrBlank()) toast(answer)
                        finishAndCleanup()
                    }
                }
            }
        })
    }

    private fun friendlyMessageFor(code: String, status: Int): String = when (code) {
        "AGENT_TIMEOUT" -> "The assistant took too long to respond. Please try again."
        "AGENT_INVALID_RESPONSE" ->
            "The assistant got confused and couldn't give a real answer. Please try again."
        "MCP_UNAVAILABLE", "PLANE_UNAVAILABLE" -> "Plane is unreachable right now."
        "UNAUTHORIZED" -> "Your API token was rejected. Open the app to sign in again."
        "EMPTY_TRANSCRIPT" -> "Didn't catch any speech in that recording."
        else -> "Something went wrong ($status). Please try again."
    }

    private fun playAnswerAudio(serverUrl: String, token: String, audioPath: String) {
        val request = Request.Builder()
            .url("$serverUrl$audioPath")
            .header("Authorization", "Bearer $token")
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = finishAndCleanup()

            override fun onResponse(call: Call, response: Response) {
                response.use { resp ->
                    if (!resp.isSuccessful) {
                        finishAndCleanup()
                        return
                    }
                    val bytes = resp.body?.bytes()
                    if (bytes == null) {
                        finishAndCleanup()
                        return
                    }
                    val playbackFile = File(cacheDir, "widget_answer_${System.currentTimeMillis()}.mp3")
                    playbackFile.writeBytes(bytes)
                    mainHandler.post { playFile(playbackFile) }
                }
            }
        })
    }

    private fun playFile(file: File) {
        try {
            val player = MediaPlayer()
            player.setDataSource(file.absolutePath)
            player.setOnCompletionListener {
                file.delete()
                it.release()
                finishAndCleanup()
            }
            player.setOnErrorListener { mp, _, _ ->
                file.delete()
                mp.release()
                finishAndCleanup()
                true
            }
            player.prepare()
            player.start()
            mediaPlayer = player
            // The answer is heard, not read -- free the screen as soon as
            // playback actually starts instead of leaving the bubble up
            // for its whole duration.
            removeOverlay()
        } catch (e: Exception) {
            file.delete()
            finishAndCleanup()
        }
    }

    // --- Cleanup -------------------------------------------------------------

    private fun finishAndCleanup() {
        mainHandler.post {
            removeOverlay()
            @Suppress("DEPRECATION")
            stopForeground(true)
            stopSelf()
        }
    }

    private fun toast(message: String) {
        mainHandler.post { Toast.makeText(this, message, Toast.LENGTH_LONG).show() }
    }

    override fun onDestroy() {
        stopRecordingRunnable?.let { mainHandler.removeCallbacks(it) }
        try {
            recorder?.stop()
        } catch (_: Exception) {
        }
        recorder?.release()
        recorder = null
        mediaPlayer?.release()
        mediaPlayer = null
        removeOverlay()
        super.onDestroy()
    }

    companion object {
        private const val NOTIFICATION_ID = 4201
        private const val CHANNEL_ID = "voice_widget"
        private const val MAX_RECORDING_MS = 30_000L
        private const val REQUEST_TIMEOUT_SECONDS = 60L

        private const val FLUTTER_PREFS_NAME = "FlutterSharedPreferences"
        private const val SERVER_URL_PREF_KEY = "flutter.server_url"
        private const val INPUT_LANGUAGE_PREF_KEY = "flutter.input_language"

        // Must match AppPreferences's widget-token key (with the
        // "flutter." prefix the shared_preferences plugin adds to every
        // key on Android) -- see AppPreferences.setWidgetToken.
        const val WIDGET_TOKEN_PREF_KEY = "flutter.widget_gateway_api_token"
    }
}
