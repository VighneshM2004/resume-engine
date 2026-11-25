import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:resume_engine_app/features/system_status/data/status_repository.dart';
import 'package:resume_engine_app/features/system_status/domain/service_status.dart';

/// Answers requests in-process, so tests never touch the network.
class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this._handler);

  final ResponseBody Function(RequestOptions options) _handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async => _handler(options);

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(int status, Object body) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
  },
);

HttpStatusRepository _repository(
  ResponseBody Function(RequestOptions options) handler,
) {
  final dio = Dio(
    BaseOptions(
      baseUrl: 'http://api.test',
      validateStatus: (status) => status != null,
    ),
  )..httpClientAdapter = _FakeAdapter(handler);
  return HttpStatusRepository(dio);
}

const _allUp = {
  'status': 'ready',
  'checks': {
    'database': {'ok': true, 'error_code': null},
    'redis': {'ok': true, 'error_code': null},
    'storage': {'ok': true, 'error_code': null},
  },
};

void main() {
  test('reports live and ready when both probes pass', () async {
    final repository = _repository(
      (options) => options.path == '/health'
          ? _json(200, {'status': 'ok'})
          : _json(200, _allUp),
    );

    final status = await repository.fetch();

    expect(status, isA<ApiReachable>());
    final reachable = status as ApiReachable;
    expect(reachable.live, isTrue);
    expect(reachable.ready, isTrue);
    expect(reachable.checks.map((c) => c.name), [
      'database',
      'redis',
      'storage',
    ]);
  });

  test('a 503 from /ready is a valid answer that names the failure', () async {
    final repository = _repository(
      (options) => options.path == '/health'
          ? _json(200, {'status': 'ok'})
          : _json(503, {
              'status': 'not_ready',
              'checks': {
                'database': {'ok': true, 'error_code': null},
                'redis': {'ok': false, 'error_code': 'REDIS_UNAVAILABLE'},
              },
            }),
    );

    final status = await repository.fetch() as ApiReachable;

    expect(status.live, isTrue);
    expect(status.ready, isFalse);
    final redis = status.checks.singleWhere((c) => c.name == 'redis');
    expect(redis.ok, isFalse);
    expect(redis.errorCode, 'REDIS_UNAVAILABLE');
  });

  test(
    'a connection failure becomes ApiUnavailable, not an exception',
    () async {
      final repository = _repository(
        (options) => throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
        ),
      );

      final status = await repository.fetch();

      expect(status, isA<ApiUnavailable>());
      expect((status as ApiUnavailable).reason, contains('http://api.test'));
    },
  );

  test('an unexpected /ready body becomes ApiUnavailable', () async {
    final repository = _repository(
      (options) => options.path == '/health'
          ? _json(200, {'status': 'ok'})
          : _json(500, {'detail': 'Internal Server Error'}),
    );

    final status = await repository.fetch();

    expect(status, isA<ApiUnavailable>());
    expect((status as ApiUnavailable).reason, contains('HTTP 500'));
  });
}
