class AgentInfo {
  final String cli;
  final String? model;

  const AgentInfo({required this.cli, this.model});

  factory AgentInfo.fromJson(Map<String, dynamic> json) {
    return AgentInfo(
      cli: json['cli'] as String? ?? 'unknown',
      model: json['model'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'cli': cli,
        if (model != null) 'model': model,
      };
}
