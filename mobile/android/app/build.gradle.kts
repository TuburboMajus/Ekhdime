plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.planeassistant.plane_assistant"
    compileSdk = flutter.compileSdkVersion
    // Several plugins (flutter_secure_storage, just_audio, record, ...)
    // require NDK 27; the Flutter tool's own default (flutter.ndkVersion)
    // is older. NDK versions are backward compatible, so pin the higher one.
    ndkVersion = "27.0.12077973"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.planeassistant.plane_assistant"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        // The `record` plugin's Android implementation requires SDK 23+
        // (Flutter's own default floor is lower); bump it explicitly.
        minSdk = 23
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    // Used only by VoiceRecordingService (the home-screen widget's
    // record-without-opening-the-app flow) to call the gateway directly
    // from native Kotlin -- there is no running Flutter engine in that
    // path for the `http` package to help with.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
