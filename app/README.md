# resume_engine_app

Flutter recruiter app (Android + web) for resume-engine. Riverpod for state
and dependency injection (ADR-014), Dio for HTTP.

## Run

Start the backend first (`make up` in the repo root, from WSL).

```bash
flutter pub get

# Web (the API allows http://localhost:8080 via CORS_ALLOWED_ORIGINS)
flutter run -d chrome --web-port 8080
# If Chrome won't launch: serve it and open http://localhost:8080 yourself
flutter run -d web-server --web-port 8080

# Android emulator: the host machine is 10.0.2.2, not localhost
flutter run -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Check (what CI runs)

```bash
dart format --output=none --set-exit-if-changed .
flutter analyze --fatal-infos
flutter test
flutter build web --release
```

## Layout

```
lib/
  main.dart                 ProviderScope + app
  app.dart                  MaterialApp, theme
  core/config/              build-time config (--dart-define)
  core/network/             the shared Dio client
  features/<feature>/
    domain/                 plain Dart models
    data/                   repositories (HTTP)
    application/            Riverpod providers
    presentation/           screens and widgets
```
