import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:resume_engine_app/features/system_status/application/status_providers.dart';
import 'package:resume_engine_app/features/system_status/data/status_repository.dart';
import 'package:resume_engine_app/features/system_status/domain/service_status.dart';
import 'package:resume_engine_app/features/system_status/presentation/system_status_screen.dart';

/// Returns queued results in order, then repeats the last one.
class _FakeRepository implements StatusRepository {
  _FakeRepository(this._results);

  final List<ServiceStatus> _results;
  int calls = 0;

  @override
  Future<ServiceStatus> fetch() async {
    final result = _results[calls < _results.length ? calls : _results.length - 1];
    calls++;
    return result;
  }
}

Future<void> _pumpScreen(WidgetTester tester, _FakeRepository repository) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [statusRepositoryProvider.overrideWithValue(repository)],
      child: const MaterialApp(home: SystemStatusScreen()),
    ),
  );
}

const _ready = ApiReachable(
  live: true,
  ready: true,
  checks: [
    DependencyCheck(name: 'database', ok: true),
    DependencyCheck(name: 'redis', ok: true),
    DependencyCheck(name: 'storage', ok: true),
  ],
);

void main() {
  testWidgets('shows a spinner, then every dependency as OK', (tester) async {
    await _pumpScreen(tester, _FakeRepository([_ready]));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    for (final name in ['database', 'redis', 'storage']) {
      expect(find.text(name), findsOneWidget);
    }
    expect(find.bySemanticsLabel('Failing'), findsNothing);
  });

  testWidgets('names the failing dependency and its error code',
      (tester) async {
    const notReady = ApiReachable(
      live: true,
      ready: false,
      checks: [
        DependencyCheck(name: 'database', ok: true),
        DependencyCheck(
          name: 'redis',
          ok: false,
          errorCode: 'REDIS_UNAVAILABLE',
        ),
      ],
    );

    await _pumpScreen(tester, _FakeRepository([notReady]));
    await tester.pumpAndSettle();

    expect(find.text('REDIS_UNAVAILABLE'), findsOneWidget);
    // /ready tile and the redis tile.
    expect(find.bySemanticsLabel('Failing'), findsNWidgets(2));
  });

  testWidgets('unreachable API shows the reason and Retry re-fetches',
      (tester) async {
    final repository = _FakeRepository([
      const ApiUnavailable('Cannot connect to http://localhost:8000'),
      _ready,
    ]);

    await _pumpScreen(tester, repository);
    await tester.pumpAndSettle();

    expect(find.text('API unavailable'), findsOneWidget);
    expect(find.textContaining('Cannot connect'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(repository.calls, 2);
    expect(find.text('API unavailable'), findsNothing);
    expect(find.text('storage'), findsOneWidget);
  });

  testWidgets('the refresh button re-fetches', (tester) async {
    final repository = _FakeRepository([_ready]);

    await _pumpScreen(tester, repository);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Refresh'));
    await tester.pumpAndSettle();

    expect(repository.calls, 2);
  });
}
