class AgentCliStatus {
  final String status;
  final String? type;

  const AgentCliStatus({required this.status, this.type});

  factory AgentCliStatus.fromJson(Map<String, dynamic> json) {
    return AgentCliStatus(
      status: json['status'] as String? ?? 'error',
      type: json['type'] as String?,
    );
  }
}

/// Response of `GET /api/v1/health/details`.
class HealthDetails {
  final String gateway;
  final String plane;
  final String planeMcp;
  final String stt;
  final String tts;
  final AgentCliStatus agentCli;

  const HealthDetails({
    required this.gateway,
    required this.plane,
    required this.planeMcp,
    required this.stt,
    required this.tts,
    required this.agentCli,
  });

  factory HealthDetails.fromJson(Map<String, dynamic> json) {
    return HealthDetails(
      gateway: json['gateway'] as String? ?? 'error',
      plane: json['plane'] as String? ?? 'error',
      planeMcp: json['plane_mcp'] as String? ?? 'error',
      stt: json['stt'] as String? ?? 'error',
      tts: json['tts'] as String? ?? 'error',
      agentCli: AgentCliStatus.fromJson(
        json['agent_cli'] as Map<String, dynamic>? ?? const {},
      ),
    );
  }

  bool get allOk =>
      gateway == 'ok' &&
      plane == 'ok' &&
      planeMcp == 'ok' &&
      stt == 'ok' &&
      tts == 'ok' &&
      agentCli.status == 'ok';
}

/// Response of `GET /api/v1/info`.
class ServerInfo {
  final String serverVersion;
  final String apiVersion;
  final Map<String, bool> features;

  const ServerInfo({
    required this.serverVersion,
    required this.apiVersion,
    required this.features,
  });

  factory ServerInfo.fromJson(Map<String, dynamic> json) {
    final rawFeatures = json['features'] as Map<String, dynamic>? ?? const {};
    return ServerInfo(
      serverVersion: json['server_version'] as String? ?? 'unknown',
      apiVersion: json['api_version'] as String? ?? 'unknown',
      features: rawFeatures.map((k, v) => MapEntry(k, v == true)),
    );
  }
}
