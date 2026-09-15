/// Validates and normalizes a user-entered gateway base URL.
///
/// Normalization: trims whitespace, strips trailing slashes. Accepts both
/// `http://` and `https://`. Rejects malformed URLs (missing scheme, missing
/// host, unsupported scheme) by throwing a [FormatException] with a message
/// suitable for display inline in a form field.
class ServerUrl {
  /// Returns the normalized URL (no trailing slash), or throws
  /// [FormatException] if [input] is not a usable http(s) URL.
  static String normalize(String input) {
    final trimmed = input.trim();
    if (trimmed.isEmpty) {
      throw const FormatException('Server URL is required.');
    }

    Uri? uri;
    try {
      uri = Uri.parse(trimmed);
    } on FormatException {
      throw const FormatException('That doesn\'t look like a valid URL.');
    }

    if (uri.scheme != 'http' && uri.scheme != 'https') {
      throw const FormatException(
        'URL must start with http:// or https://',
      );
    }

    if (uri.host.isEmpty) {
      throw const FormatException('URL must include a host, e.g. 192.168.1.20:8088.');
    }

    var normalized = uri.toString();
    while (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }
    return normalized;
  }

  /// Like [normalize] but returns null instead of throwing, for callers that
  /// just want a validity check.
  static String? tryNormalize(String input) {
    try {
      return normalize(input);
    } on FormatException {
      return null;
    }
  }
}
