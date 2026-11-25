import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/app_config.dart';

/// The one HTTP client the app uses. Auth and retry interceptors attach
/// here in M5, so every repository gets them without changes.
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 10),
      // Repositories interpret status codes themselves (a 503 from /ready
      // is a valid answer, not a transport failure).
      validateStatus: (status) => status != null,
    ),
  );
  ref.onDispose(dio.close);
  return dio;
});
