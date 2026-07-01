// Generated from google-services.json for project trade-signals-771a6
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) throw UnsupportedError('Web not configured for Firebase.');
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        throw UnsupportedError('iOS FirebaseOptions not configured yet.');
      default:
        throw UnsupportedError(
            'Unsupported platform: $defaultTargetPlatform');
    }
  }

  static const FirebaseOptions android = FirebaseOptions(
    apiKey:            'AIzaSyCjA54PRKtnL9jym4UC6IHuJSznZcvJNY0',
    appId:             '1:993438890457:android:2a8f0e545bb43bdd0ec1c8',
    messagingSenderId: '993438890457',
    projectId:         'trade-signals-771a6',
    storageBucket:     'trade-signals-771a6.firebasestorage.app',
  );
}
