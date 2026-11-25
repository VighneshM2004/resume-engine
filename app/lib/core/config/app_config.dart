/// Build-time configuration, set with `--dart-define`.
///
/// Example for the Android emulator, which reaches the host machine
/// through 10.0.2.2 rather than localhost:
///
///     flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
abstract final class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );
}
