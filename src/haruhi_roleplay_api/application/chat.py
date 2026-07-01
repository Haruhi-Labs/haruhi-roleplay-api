"""Chat use cases and minimal roleplay orchestration."""

from __future__ import annotations

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    ChatInput,
    ChatOutput,
    DTOValidationError,
    PromptBuildInput,
    RequestId,
    Visibility,
    model_messages_from_prompt,
)
from haruhi_roleplay_api.ports import ChatModelRouter, PersonaRepository, PromptBuilder


class SendChatMessageUseCase:
    def __init__(self, orchestrator: "RoleplayOrchestrator") -> None:
        self._orchestrator = orchestrator

    def execute(self, chat_input: ChatInput) -> ChatOutput:
        return self._orchestrator.run(chat_input)


class RoleplayOrchestrator:
    def __init__(
        self,
        *,
        persona_repository: PersonaRepository,
        prompt_builder: PromptBuilder,
        model_router: ChatModelRouter,
    ) -> None:
        self._persona_repository = persona_repository
        self._prompt_builder = prompt_builder
        self._model_router = model_router

    def run(self, chat_input: ChatInput) -> ChatOutput:
        _ensure_v1_capabilities(chat_input)
        if chat_input.requestId is None:
            raise DTOValidationError("requestId is required")

        character = _find_public_character(self._persona_repository, chat_input)
        persona = _find_public_persona(
            self._persona_repository,
            chat_input,
        )
        prompt_output = self._prompt_builder.build(
            PromptBuildInput(
                character=character,
                persona=persona,
                userMessage=chat_input.message,
                capabilities=chat_input.capabilities,
                generation=chat_input.generation,
            )
        )
        model_response = self._model_router.generate(
            model_messages_from_prompt(prompt_output.messages),
            chat_input.generation,
        )

        return ChatOutput(
            requestId=RequestId(str(chat_input.requestId)),
            characterId=chat_input.characterId,
            personaMode=chat_input.personaMode,
            reply=model_response.reply,
            usage={
                **model_response.usage.to_mapping(),
                "provider": model_response.provider,
                "model": model_response.model,
            },
            rag={"enabled": False},
            memory={"enabled": False},
            safety={
                "enabled": chat_input.capabilities.safetyFilter,
                "blocked": False,
            },
            debug=model_response.debug if chat_input.capabilities.debugTrace else None,
        )


def _ensure_v1_capabilities(chat_input: ChatInput) -> None:
    if chat_input.capabilities.stream:
        raise DTOValidationError("capabilities.stream is not supported by /v1/chat")
    if chat_input.capabilities.continuousSession:
        raise DTOValidationError(
            "capabilities.continuousSession is not supported by chat v1"
        )
    if chat_input.capabilities.rag:
        raise DTOValidationError("capabilities.rag is not supported by chat v1")
    if chat_input.capabilities.memory:
        raise DTOValidationError("capabilities.memory is not supported by chat v1")


def _find_public_character(repository: PersonaRepository, chat_input: ChatInput):
    for character in repository.list_characters():
        if character.characterId == chat_input.characterId:
            if character.visibility is Visibility.PUBLIC:
                return character
            break
    raise AppError(
        code=ErrorCode.PERSONA_NOT_FOUND,
        message=f"Character was not found: {chat_input.characterId}",
    )


def _find_public_persona(
    repository: PersonaRepository,
    chat_input: ChatInput,
):
    for preset in repository.list_presets(chat_input.characterId):
        if (
            preset.personaMode == chat_input.personaMode
            and preset.visibility is Visibility.PUBLIC
        ):
            return preset
    raise AppError(
        code=ErrorCode.PERSONA_MODE_NOT_FOUND,
        message=f"Persona preset was not found: {chat_input.personaMode}",
    )
