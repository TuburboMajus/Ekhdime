System prompt for tests.
{% if user_identity %}
User: {{ user_identity }}
{% endif %}
{% if current_datetime %}
Now: {{ current_datetime }}
{% endif %}
{% if conversation_history %}
History:
{{ conversation_history }}
{% endif %}
Query: {{ user_query }}
