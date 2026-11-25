import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../data/status_repository.dart';
import '../domain/service_status.dart';

/// Overridden with a fake in widget tests.
final statusRepositoryProvider = Provider<StatusRepository>(
  (ref) => HttpStatusRepository(ref.watch(dioProvider)),
);

/// Re-fetched by invalidating it (the screen's refresh and retry buttons).
final serviceStatusProvider = FutureProvider.autoDispose<ServiceStatus>(
  (ref) => ref.watch(statusRepositoryProvider).fetch(),
);
