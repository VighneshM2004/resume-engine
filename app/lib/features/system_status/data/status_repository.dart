import 'package:dio/dio.dart';

import '../domain/service_status.dart';

abstract interface class StatusRepository {
  /// Never throws for network or API problems: those become [ApiUnavailable]
  /// so the screen can show them instead of crashing.
  Future<ServiceStatus> fetch();
}

final class HttpStatusRepository implements StatusRepository {
  HttpStatusRepository(this._dio);

  final Dio _dio;

  @override
  Future<ServiceStatus> fetch() async {
    final List<Response<Object?>> responses;
    try {
      responses = await Future.wait([
        _dio.get<Object?>('/health'),
        _dio.get<Object?>('/ready'),
      ]);
    } on DioException catch (e) {
      return ApiUnavailable(_describe(e));
    }
    return _parse(health: responses[0], ready: responses[1]);
  }

  ServiceStatus _parse({
    required Response<Object?> health,
    required Response<Object?> ready,
  }) {
    final healthBody = health.data;
    final live =
        health.statusCode == 200 &&
        healthBody is Map<String, Object?> &&
        healthBody['status'] == 'ok';

    final readyBody = ready.data;
    final readyStatus = ready.statusCode;
    if ((readyStatus != 200 && readyStatus != 503) ||
        readyBody is! Map<String, Object?>) {
      return ApiUnavailable(
        'Unexpected response from /ready (HTTP $readyStatus)',
      );
    }

    final rawChecks = readyBody['checks'];
    if (rawChecks is! Map<String, Object?>) {
      return const ApiUnavailable('Unexpected response from /ready');
    }

    final checks = <DependencyCheck>[
      for (final MapEntry(:key, :value) in rawChecks.entries)
        if (value is Map<String, Object?>)
          DependencyCheck(
            name: key,
            ok: value['ok'] == true,
            errorCode: switch (value['error_code']) {
              final String code => code,
              _ => null,
            },
          ),
    ];

    return ApiReachable(
      live: live,
      ready: readyStatus == 200 && readyBody['status'] == 'ready',
      checks: checks,
    );
  }

  String _describe(DioException e) => switch (e.type) {
    DioExceptionType.connectionTimeout ||
    DioExceptionType.sendTimeout ||
    DioExceptionType.receiveTimeout => 'The API did not respond in time',
    DioExceptionType.connectionError =>
      'Cannot connect to ${_dio.options.baseUrl}',
    _ => 'Request to the API failed',
  };
}
