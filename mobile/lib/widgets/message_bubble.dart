import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../models/message.dart';

/// Renders a single chat message: right-aligned plain text for the user,
/// left-aligned Markdown for the assistant, with Copy/Speak/Retry actions
/// on assistant messages.
class MessageBubble extends StatelessWidget {
  final Message message;
  final VoidCallback? onCopy;
  final VoidCallback? onSpeak;
  final VoidCallback? onRetry;
  final bool isSpeaking;

  const MessageBubble({
    super.key,
    required this.message,
    this.onCopy,
    this.onSpeak,
    this.onRetry,
    this.isSpeaking = false,
  });

  bool get _isUser => message.role == MessageRole.user;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final bubbleColor = _isUser
        ? colorScheme.primary
        : (message.isError
            ? colorScheme.errorContainer
            : colorScheme.surfaceContainerHighest);
    final textColor = _isUser
        ? colorScheme.onPrimary
        : (message.isError ? colorScheme.onErrorContainer : colorScheme.onSurface);

    return Align(
      alignment: _isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.8,
        ),
        child: Column(
          crossAxisAlignment:
              _isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            if (!_isUser && !message.isPending && (message.reasoning?.trim().isNotEmpty ?? false))
              _ReasoningSection(reasoning: message.reasoning!),
            if (_isUser && message.isVoiceInput) _VoiceInputHint(color: colorScheme.onSurfaceVariant),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: bubbleColor,
                borderRadius: BorderRadius.circular(16),
              ),
              child: message.isPending
                  ? _ThinkingIndicator(color: textColor)
                  : (_isUser
                      ? Text(
                          message.content,
                          style: TextStyle(color: textColor),
                        )
                      : MarkdownBody(
                          data: message.content,
                          selectable: true,
                          styleSheet: MarkdownStyleSheet.fromTheme(theme).copyWith(
                            p: TextStyle(color: textColor),
                          ),
                        )),
            ),
            if (!_isUser && !message.isPending)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (onCopy != null)
                      _ActionIcon(
                        icon: Icons.copy_rounded,
                        tooltip: 'Copy',
                        onPressed: onCopy,
                      ),
                    if (onSpeak != null)
                      _ActionIcon(
                        icon: isSpeaking
                            ? Icons.volume_up_rounded
                            : Icons.volume_up_outlined,
                        tooltip: 'Speak',
                        onPressed: onSpeak,
                      ),
                    if (onRetry != null)
                      _ActionIcon(
                        icon: Icons.refresh_rounded,
                        tooltip: 'Retry',
                        onPressed: onRetry,
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Small "sent by voice" caption shown above a user bubble whose content
/// came from a transcribed recording rather than typed text -- the only
/// way to tell the two apart, since both render as plain text otherwise.
class _VoiceInputHint extends StatelessWidget {
  final Color color;
  const _VoiceInputHint({required this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2, right: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.mic_rounded, size: 13, color: color),
          const SizedBox(width: 3),
          Text('Sent by voice', style: TextStyle(fontSize: 11, color: color)),
        ],
      ),
    );
  }
}

class _ActionIcon extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  const _ActionIcon({required this.icon, required this.tooltip, this.onPressed});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: Icon(icon, size: 18),
      tooltip: tooltip,
      visualDensity: VisualDensity.compact,
      onPressed: onPressed,
    );
  }
}

/// Collapsed-by-default "Thinking" disclosure for a model's chain-of-thought
/// (`Message.reasoning`), shown above the answer bubble -- the same pattern
/// as Claude.ai/ChatGPT: reasoning is available on demand but never clutters
/// the primary response by default.
class _ReasoningSection extends StatefulWidget {
  final String reasoning;
  const _ReasoningSection({required this.reasoning});

  @override
  State<_ReasoningSection> createState() => _ReasoningSectionState();
}

class _ReasoningSectionState extends State<_ReasoningSection> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final mutedColor = theme.colorScheme.onSurfaceVariant;

    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      constraints: const BoxConstraints(minWidth: 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            key: const Key('reasoning_toggle'),
            borderRadius: BorderRadius.circular(8),
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.psychology_outlined, size: 15, color: mutedColor),
                  const SizedBox(width: 4),
                  Text(
                    'Thinking',
                    style: theme.textTheme.labelMedium?.copyWith(color: mutedColor),
                  ),
                  Icon(
                    _expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                    size: 18,
                    color: mutedColor,
                  ),
                ],
              ),
            ),
          ),
          if (_expanded)
            Container(
              key: const Key('reasoning_content'),
              margin: const EdgeInsets.only(left: 4, right: 4, bottom: 4),
              padding: const EdgeInsets.all(10),
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.76,
              ),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHigh,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                widget.reasoning,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: mutedColor,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ThinkingIndicator extends StatelessWidget {
  final Color color;
  const _ThinkingIndicator({required this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 14,
          height: 14,
          child: CircularProgressIndicator(strokeWidth: 2, color: color),
        ),
        const SizedBox(width: 10),
        Text('Thinking...', style: TextStyle(color: color)),
      ],
    );
  }
}
