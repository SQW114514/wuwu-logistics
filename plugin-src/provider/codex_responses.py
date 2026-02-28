from collections.abc import Mapping

from dify_plugin import ModelProvider


class CodexResponsesProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        # Keep provider validation minimal: many responses-only gateways reject
        # chat/completions or model list checks used by generic OpenAI plugins.
        return
