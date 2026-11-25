/// What the app knows about the API's health, from GET /health and /ready.
sealed class ServiceStatus {
  const ServiceStatus();
}

/// The API answered both probes.
final class ApiReachable extends ServiceStatus {
  const ApiReachable({
    required this.live,
    required this.ready,
    required this.checks,
  });

  /// GET /health returned 200: the process is up.
  final bool live;

  /// GET /ready returned 200: every dependency is usable.
  final bool ready;

  /// One entry per dependency reported by /ready.
  final List<DependencyCheck> checks;
}

/// The API could not be reached, or answered with something unexpected.
final class ApiUnavailable extends ServiceStatus {
  const ApiUnavailable(this.reason);

  /// Human-readable cause, safe to show on screen.
  final String reason;
}

final class DependencyCheck {
  const DependencyCheck({
    required this.name,
    required this.ok,
    this.errorCode,
  });

  final String name;
  final bool ok;

  /// Stable code from the API (e.g. REDIS_UNAVAILABLE); null when ok.
  final String? errorCode;
}
