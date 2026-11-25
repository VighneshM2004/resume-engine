import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../application/status_providers.dart';
import '../domain/service_status.dart';

/// Shows whether the API and its dependencies are up. M0's only screen; it
/// proves the app → API → Postgres/Redis/storage path end to end.
class SystemStatusScreen extends ConsumerWidget {
  const SystemStatusScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(serviceStatusProvider);
    void refresh() => ref.invalidate(serviceStatusProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('System status'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: refresh,
          ),
        ],
      ),
      body: status.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => _Unavailable(
          reason: 'Something went wrong',
          onRetry: refresh,
        ),
        data: (value) => switch (value) {
          ApiUnavailable(:final reason) =>
            _Unavailable(reason: reason, onRetry: refresh),
          final ApiReachable reachable => _StatusList(status: reachable),
        },
      ),
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable({required this.reason, required this.onRetry});

  final String reason;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48),
            const SizedBox(height: 16),
            Text(
              'API unavailable',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(reason, textAlign: TextAlign.center),
            const SizedBox(height: 24),
            FilledButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _StatusList extends StatelessWidget {
  const _StatusList({required this.status});

  final ApiReachable status;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        _StatusTile(label: 'API process (/health)', ok: status.live),
        _StatusTile(label: 'Ready for traffic (/ready)', ok: status.ready),
        const Divider(),
        for (final check in status.checks)
          _StatusTile(
            label: check.name,
            ok: check.ok,
            detail: check.errorCode,
          ),
      ],
    );
  }
}

class _StatusTile extends StatelessWidget {
  const _StatusTile({required this.label, required this.ok, this.detail});

  final String label;
  final bool ok;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return ListTile(
      leading: Icon(
        ok ? Icons.check_circle : Icons.error,
        color: ok ? colors.primary : colors.error,
        semanticLabel: ok ? 'OK' : 'Failing',
      ),
      title: Text(label),
      subtitle: detail == null ? null : Text(detail!),
    );
  }
}
