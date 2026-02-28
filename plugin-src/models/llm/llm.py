from __future__ import annotations

import json
import re
from collections.abc import Generator, Mapping
from typing import Any, Optional, Union, cast

import tiktoken
from openai import OpenAI, Stream
from openai.types.responses import Response, ResponseStreamEvent

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import AIModelEntity, FetchFrom, ModelType
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeError,
)

from ..common_openai import _CommonOpenAI


class CodexResponsesLargeLanguageModel(_CommonOpenAI, LargeLanguageModel):
    _TIER_SUFFIX_PATTERN = re.compile(
        r"-(?:medium|high|xhigh)(?:-(?:medium|high|xhigh))?$",
        re.IGNORECASE,
    )
    _TIER_VALUE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        if model_parameters.pop("enable_stream", None) is False:
            stream = False

        model = self._resolve_model_with_performance_tier(
            model,
            model_parameters.pop("performance_tier", "auto"),
            model_parameters.pop("custom_performance_tier", ""),
        )

        response_payload = self._build_responses_payload(
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            user=user,
        )

        client = OpenAI(**self._to_credential_kwargs(credentials))
        response = self._with_invoke_error_mapping(
            lambda: client.responses.create(
                model=model,
                stream=stream,
                **response_payload,
            )
        )

        if stream:
            return self._handle_responses_stream_response(
                model=model,
                credentials=credentials,
                response=cast(Stream[ResponseStreamEvent], response),
                prompt_messages=prompt_messages,
                tools=tools,
            )

        return self._handle_responses_response(
            model=model,
            credentials=credentials,
            response=cast(Response, response),
            prompt_messages=prompt_messages,
            tools=tools,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            client = OpenAI(**self._to_credential_kwargs(credentials))
            client.responses.create(
                model=model,
                input="ping",
                max_output_tokens=16,
                stream=False,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        template = self._pick_template_model()
        return self._build_model_entity_from_template(model, template)

    def remote_models(self, credentials: dict) -> list[AIModelEntity]:
        """
        Auto-discover remote model ids from the provider /models endpoint.
        Dify can surface these discovered models in the model list.
        """
        template = self._pick_template_model()
        client = OpenAI(**self._to_credential_kwargs(credentials))

        listed_models = self._with_invoke_error_mapping(lambda: client.models.list())
        remote_items = getattr(listed_models, "data", listed_models) or []

        entities: list[AIModelEntity] = []
        seen: set[str] = set()
        for item in remote_items:
            model_id = getattr(item, "id", "")
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            entities.append(self._build_model_entity_from_template(model_id, template))

        return entities

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        text = "\n".join(
            part for message in prompt_messages for part in [self._extract_text(message)] if part
        )
        if not text:
            return 0

        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")

        token_count = len(encoding.encode(text))

        if tools:
            for tool in tools:
                token_count += len(encoding.encode(tool.name or ""))
                token_count += len(encoding.encode(tool.description or ""))
                token_count += len(encoding.encode(json.dumps(tool.parameters or {})))

        return token_count

    def _build_responses_payload(
        self,
        *,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        stop: Optional[list[str]],
        user: Optional[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input": self._convert_prompt_messages_to_responses_input(prompt_messages),
        }

        if "temperature" in model_parameters:
            payload["temperature"] = model_parameters["temperature"]
        if "top_p" in model_parameters:
            payload["top_p"] = model_parameters["top_p"]
        if "max_tokens" in model_parameters:
            payload["max_output_tokens"] = model_parameters["max_tokens"]
        elif "max_completion_tokens" in model_parameters:
            payload["max_output_tokens"] = model_parameters["max_completion_tokens"]

        reasoning_effort = model_parameters.get("reasoning_effort")
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}

        verbosity = model_parameters.get("verbosity")
        if verbosity:
            payload["text"] = {"verbosity": verbosity}

        if tools:
            payload["tools"] = [self._convert_tool_to_response_tool(tool) for tool in tools]
            payload["tool_choice"] = "auto"

        if stop:
            payload["stop"] = stop
        # Some OpenAI-compatible gateways reject the `user` parameter on
        # /responses. Keep compatibility by not sending it.

        return payload

    def _pick_template_model(self) -> AIModelEntity:
        predefined_models = self.predefined_models()
        if not predefined_models:
            raise ValueError("No predefined model schema found")
        return next(
            (item for item in predefined_models if item.model == "gpt-5.2"),
            predefined_models[0],
        )

    def _build_model_entity_from_template(
        self,
        model_id: str,
        template: AIModelEntity,
    ) -> AIModelEntity:
        features = list(template.features or [])
        model_properties = template.model_properties or {}
        if hasattr(model_properties, "items"):
            model_properties = dict(model_properties.items())
        else:
            model_properties = dict(model_properties)
        parameter_rules = list(template.parameter_rules or [])

        return AIModelEntity(
            model=model_id,
            label=I18nObject(en_US=model_id, zh_Hans=model_id),
            model_type=ModelType.LLM,
            features=features,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties=model_properties,
            parameter_rules=parameter_rules,
            pricing=template.pricing,
        )

    def _resolve_model_with_performance_tier(
        self,
        model: str,
        tier_value: Any,
        custom_tier_value: Any,
    ) -> str:
        custom_tier = str(custom_tier_value or "").strip().lower().lstrip("-")
        if custom_tier:
            tier = custom_tier
        else:
            tier = str(tier_value or "auto").strip().lower()

        if tier in {"", "auto"}:
            return model
        if not self._TIER_VALUE_PATTERN.fullmatch(tier):
            return model

        base_model = self._TIER_SUFFIX_PATTERN.sub("", model)
        return f"{base_model}-{tier}"

    def _convert_prompt_messages_to_responses_input(
        self,
        prompt_messages: list[PromptMessage],
    ) -> list[dict[str, Any]]:
        input_messages: list[dict[str, Any]] = []

        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                content = self._extract_text(message)
                if content:
                    input_messages.append({"role": "developer", "content": content})
                continue

            if isinstance(message, UserPromptMessage):
                if isinstance(message.content, str):
                    input_messages.append({"role": "user", "content": message.content})
                else:
                    content_parts: list[dict[str, Any]] = []
                    for item in message.content or []:
                        if isinstance(item, TextPromptMessageContent):
                            content_parts.append(
                                {
                                    "type": "input_text",
                                    "text": item.data,
                                }
                            )
                        elif isinstance(item, ImagePromptMessageContent):
                            image_url = item.url if item.url else item.data
                            image_part: dict[str, Any] = {
                                "type": "input_image",
                                "image_url": image_url,
                            }
                            if item.detail:
                                image_part["detail"] = item.detail.value
                            content_parts.append(image_part)
                    if content_parts:
                        input_messages.append({"role": "user", "content": content_parts})
                continue

            if isinstance(message, AssistantPromptMessage):
                assistant_text = self._extract_text(message)
                if assistant_text:
                    input_messages.append({"role": "assistant", "content": assistant_text})

                for tool_call in message.tool_calls or []:
                    input_messages.append(
                        {
                            "type": "function_call",
                            "call_id": tool_call.id or tool_call.function.name,
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments or "{}",
                        }
                    )
                continue

            if isinstance(message, ToolPromptMessage):
                tool_output = self._extract_text(message)
                input_messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": tool_output or "",
                    }
                )
                continue

            text = self._extract_text(message)
            if text:
                input_messages.append({"role": "user", "content": text})

        return input_messages

    def _convert_tool_to_response_tool(self, tool: PromptMessageTool) -> dict[str, Any]:
        parameters: Any = tool.parameters
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                parameters = {"type": "object", "properties": {}}
        elif not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}

        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description or "",
            "parameters": parameters,
        }

    def _handle_responses_response(
        self,
        model: str,
        credentials: dict,
        response: Response,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> LLMResult:
        content = getattr(response, "output_text", None) or self._extract_response_text(response)
        tool_calls = self._extract_response_tool_calls(response)

        assistant_prompt_message = AssistantPromptMessage(
            content=content,
            tool_calls=tool_calls,
        )

        usage = self._build_usage(
            model=model,
            credentials=credentials,
            response=response,
            prompt_messages=prompt_messages,
            assistant_prompt_message=assistant_prompt_message,
            tools=tools,
        )

        return LLMResult(
            model=getattr(response, "model", model),
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=getattr(response, "id", ""),
        )

    def _handle_responses_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[ResponseStreamEvent],
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> Generator[LLMResultChunk, None, None]:
        full_text = ""
        index = 0
        tool_calls: list[AssistantPromptMessage.ToolCall] = []

        pending_tool_calls: dict[str, dict[str, str]] = {}
        current_tool_call: Optional[str] = None
        final_response: Optional[Response] = None

        for event in response:
            event_type = getattr(event, "type", "")

            if event_type == "response.output_text.delta":
                delta_text = getattr(event, "delta", "")
                if not delta_text:
                    continue

                full_text += delta_text
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=getattr(event, "item_id", ""),
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=AssistantPromptMessage(content=delta_text),
                    ),
                )
                index += 1
                continue

            if event_type == "response.output_item.added":
                item = getattr(event, "item", None)
                if item and getattr(item, "type", "") == "function_call":
                    call_id = getattr(item, "call_id", "")
                    function_name = getattr(item, "name", "")
                    if call_id:
                        pending_tool_calls[call_id] = {
                            "name": function_name,
                            "arguments": "",
                        }
                        current_tool_call = call_id
                continue

            if event_type == "response.function_call_arguments.delta":
                delta_args = getattr(event, "delta", "")
                call_id = getattr(event, "item_id", "") or current_tool_call
                if delta_args and call_id and call_id in pending_tool_calls:
                    pending_tool_calls[call_id]["arguments"] += delta_args
                continue

            if event_type == "response.function_call_arguments.done":
                call_id = getattr(event, "item_id", "") or current_tool_call
                final_args = getattr(event, "arguments", "")
                if call_id and call_id in pending_tool_calls and isinstance(final_args, str):
                    pending_tool_calls[call_id]["arguments"] = final_args
                continue

            if event_type == "response.output_item.done":
                item = getattr(event, "item", None)
                if not item or getattr(item, "type", "") != "function_call":
                    continue

                call_id = getattr(item, "call_id", "")
                function_name = getattr(item, "name", "")
                fallback_arguments = getattr(item, "arguments", "") or "{}"

                arguments = fallback_arguments
                if call_id and call_id in pending_tool_calls:
                    arguments = pending_tool_calls[call_id].get("arguments") or fallback_arguments

                if function_name:
                    tool_call = self._build_tool_call(
                        function_name=function_name,
                        call_id=call_id,
                        arguments=arguments,
                    )
                    tool_calls.append(tool_call)

                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        system_fingerprint=call_id,
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=AssistantPromptMessage(content="", tool_calls=[tool_call]),
                        ),
                    )
                    index += 1

                if call_id in pending_tool_calls:
                    del pending_tool_calls[call_id]
                if call_id == current_tool_call:
                    current_tool_call = None
                continue

            if event_type == "response.completed":
                final_response = getattr(event, "response", None)

        usage = self._build_usage(
            model=model,
            credentials=credentials,
            response=final_response,
            prompt_messages=prompt_messages,
            assistant_prompt_message=AssistantPromptMessage(content=full_text, tool_calls=tool_calls),
            tools=tools,
        )

        finish_reason = "tool_calls" if tool_calls and not full_text.strip() else "stop"
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            system_fingerprint=getattr(final_response, "id", ""),
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=""),
                finish_reason=finish_reason,
                usage=usage,
            ),
        )

    def _build_usage(
        self,
        *,
        model: str,
        credentials: dict,
        response: Optional[Response],
        prompt_messages: list[PromptMessage],
        assistant_prompt_message: AssistantPromptMessage,
        tools: Optional[list[PromptMessageTool]],
    ):
        prompt_tokens = 0
        completion_tokens = 0

        response_usage = getattr(response, "usage", None)
        if response_usage:
            prompt_tokens = (
                getattr(response_usage, "input_tokens", None)
                or getattr(response_usage, "prompt_tokens", None)
                or 0
            )
            completion_tokens = (
                getattr(response_usage, "output_tokens", None)
                or getattr(response_usage, "completion_tokens", None)
                or 0
            )

        if not prompt_tokens:
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages, tools)
        if not completion_tokens:
            completion_tokens = self.get_num_tokens(
                model,
                credentials,
                [assistant_prompt_message],
            )

        return self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _extract_response_text(self, response: Response) -> str:
        output = getattr(response, "output", None)
        if not output:
            return ""

        chunks: list[str] = []
        for item in output:
            item_type = getattr(item, "type", "")
            if item_type == "message":
                for content in getattr(item, "content", []) or []:
                    content_type = getattr(content, "type", "")
                    if content_type in ("output_text", "text", "input_text"):
                        text_value = getattr(content, "text", "")
                        if text_value:
                            chunks.append(text_value)
                continue

            if item_type in ("output_text", "text"):
                text_value = getattr(item, "text", "")
                if text_value:
                    chunks.append(text_value)

        return "".join(chunks)

    def _extract_response_tool_calls(
        self,
        response: Response,
    ) -> list[AssistantPromptMessage.ToolCall]:
        tool_calls: list[AssistantPromptMessage.ToolCall] = []

        output = getattr(response, "output", None)
        if not output:
            return tool_calls

        for item in output:
            if getattr(item, "type", "") != "function_call":
                continue

            function_name = getattr(item, "name", "")
            if not function_name:
                continue

            arguments = getattr(item, "arguments", "{}")
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments)
            elif not isinstance(arguments, str):
                arguments = "{}"

            call_id = getattr(item, "call_id", "") or getattr(item, "id", "")
            tool_calls.append(
                self._build_tool_call(
                    function_name=function_name,
                    call_id=call_id,
                    arguments=arguments,
                )
            )

        return tool_calls

    def _build_tool_call(
        self,
        *,
        function_name: str,
        call_id: str,
        arguments: str,
    ) -> AssistantPromptMessage.ToolCall:
        return AssistantPromptMessage.ToolCall(
            id=call_id or function_name,
            type="function",
            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                name=function_name,
                arguments=arguments or "{}",
            ),
        )

    def _extract_text(self, message: PromptMessage) -> str:
        if isinstance(message.content, str):
            return message.content

        if not isinstance(message.content, list):
            return ""

        chunks: list[str] = []
        for item in message.content:
            if isinstance(item, TextPromptMessageContent):
                chunks.append(item.data)
                continue

            if getattr(item, "type", None) == PromptMessageContentType.TEXT and hasattr(item, "data"):
                chunks.append(cast(str, item.data))

        return "\n".join(chunk for chunk in chunks if chunk)

    def _with_invoke_error_mapping(self, fn):
        try:
            return fn()
        except Exception as ex:
            for mapped_error, openai_errors in self._invoke_error_mapping.items():
                if isinstance(ex, tuple(openai_errors)):
                    raise mapped_error(str(ex))
            raise InvokeError(str(ex))
