import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:plane_assistant/models/message.dart';
import 'package:plane_assistant/widgets/message_bubble.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('assistant message with reasoning shows a collapsed Thinking section by default',
      (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.assistant,
      content: 'You have 3 projects.',
      createdAt: DateTime.now(),
      metadata: const {'reasoning': 'The user wants a project list. I will call list_projects.'},
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));

    expect(find.text('Thinking'), findsOneWidget);
    // Collapsed by default: the reasoning text itself is not rendered yet.
    expect(find.byKey(const Key('reasoning_content')), findsNothing);
    expect(
      find.text('The user wants a project list. I will call list_projects.'),
      findsNothing,
    );
  });

  testWidgets('tapping the Thinking toggle reveals the reasoning text', (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.assistant,
      content: 'You have 3 projects.',
      createdAt: DateTime.now(),
      metadata: const {'reasoning': 'The user wants a project list. I will call list_projects.'},
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));
    await tester.tap(find.byKey(const Key('reasoning_toggle')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('reasoning_content')), findsOneWidget);
    expect(
      find.text('The user wants a project list. I will call list_projects.'),
      findsOneWidget,
    );

    // Tapping again collapses it.
    await tester.tap(find.byKey(const Key('reasoning_toggle')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('reasoning_content')), findsNothing);
  });

  testWidgets('assistant message without reasoning shows no Thinking section', (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.assistant,
      content: 'Hello.',
      createdAt: DateTime.now(),
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));

    expect(find.text('Thinking'), findsNothing);
  });

  testWidgets('user messages never show a Thinking section even with reasoning metadata',
      (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.user,
      content: 'list my projects',
      createdAt: DateTime.now(),
      metadata: const {'reasoning': 'should never apply to user messages'},
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));

    expect(find.text('Thinking'), findsNothing);
  });

  testWidgets('voice-originated user message shows a "Sent by voice" hint', (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.user,
      content: 'list all my projects',
      createdAt: DateTime.now(),
      isVoiceInput: true,
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));

    expect(find.text('Sent by voice'), findsOneWidget);
  });

  testWidgets('typed user message shows no voice hint', (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.user,
      content: 'list all my projects',
      createdAt: DateTime.now(),
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));

    expect(find.text('Sent by voice'), findsNothing);
  });

  testWidgets('pending assistant message shows the loading indicator, not Thinking',
      (tester) async {
    final message = Message(
      id: '1',
      role: MessageRole.assistant,
      content: '',
      createdAt: DateTime.now(),
      isPending: true,
      metadata: const {'reasoning': 'should not show while pending'},
    );

    await tester.pumpWidget(wrap(MessageBubble(message: message)));

    expect(find.text('Thinking...'), findsOneWidget); // the loading indicator
    expect(find.text('Thinking'), findsNothing); // not the reasoning toggle
  });
}
