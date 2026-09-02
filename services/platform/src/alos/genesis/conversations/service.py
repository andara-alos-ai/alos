from uuid import UUID

from alos.genesis.analysis.models import GenesisAnalyzeRequest
from alos.genesis.analysis.service import GenesisAnalyzeService
from alos.genesis.conversations.models import (
    GenesisArtifactVersionView,
    GenesisConversationCreate,
    GenesisConversationListItem,
    GenesisConversationView,
    GenesisMessageCreate,
)
from alos.genesis.conversations.repository import GenesisConversationStore
from alos.genesis.models import GenesisFieldDiff
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied, require_any_role


class GenesisConversationService:
    """Multi-turn design-time conversation service for Genesis Command Center."""

    def __init__(
        self,
        store: GenesisConversationStore,
        analyze_service: GenesisAnalyzeService,
    ) -> None:
        self._store = store
        self._analyze = analyze_service

    def create_conversation(
        self,
        request: GenesisConversationCreate,
        principal: Principal,
    ) -> GenesisConversationView:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
        )
        if (
            request.project_id is not None
            and principal.project_ids
            and request.project_id not in principal.project_ids
        ):
            raise AuthorizationDenied("Project Genesis berada di luar penugasan akun")

        conv = self._store.create_conversation(
            organization_id=principal.organization_id,
            created_by_user_id=principal.user_id,
            title=request.title,
            project_id=request.project_id,
            context_data={
                "division_code": request.division_code,
                "source_references": list(request.source_references),
            },
        )

        if request.initial_prompt and request.initial_prompt.strip():
            prompt = request.initial_prompt.strip()
            analysis_result = self._analyze.analyze(
                GenesisAnalyzeRequest(
                    prompt=prompt,
                    source_references=request.source_references,
                    division_code=request.division_code,
                ),
                principal,
            )
            return self._store.record_turn(
                conversation_id=conv.conversation_id,
                user_id=principal.user_id,
                user_message=prompt,
                assistant_message=analysis_result.understanding,
                analysis_result=analysis_result,
                source_references=request.source_references,
                diff=(),
            )

        return conv

    def list_conversations(
        self,
        principal: Principal,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[GenesisConversationListItem, ...]:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        return self._store.list_conversations(
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
        )

    def get_conversation(
        self,
        conversation_id: UUID,
        principal: Principal,
    ) -> GenesisConversationView:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        conv = self._store.get_conversation(
            principal.organization_id,
            conversation_id,
        )
        if not conv:
            raise KeyError("Genesis conversation tidak ditemukan")
        return conv

    def post_message(
        self,
        conversation_id: UUID,
        request: GenesisMessageCreate,
        principal: Principal,
    ) -> GenesisConversationView:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
        )

        conv = self.get_conversation(conversation_id, principal)
        if conv.status.value != "ACTIVE":
            raise ValueError("Conversation Genesis yang sudah ditutup tidak dapat diubah")

        prompt = request.message_text.strip()
        analysis_result = self._analyze.analyze(
            GenesisAnalyzeRequest(
                prompt=prompt,
                source_references=request.source_references,
                division_code=request.division_code,
            ),
            principal,
        )
        previous_spec = conv.artifact_versions[-1].spec_data if conv.artifact_versions else None
        current_spec = analysis_result.model_dump(mode="json")
        return self._store.record_turn(
            conversation_id=conversation_id,
            user_id=principal.user_id,
            user_message=prompt,
            assistant_message=analysis_result.understanding,
            analysis_result=analysis_result,
            source_references=request.source_references,
            diff=self._build_diff(previous_spec, current_spec),
        )

    @staticmethod
    def _build_diff(
        previous: dict[str, object] | None,
        current: dict[str, object],
    ) -> tuple[GenesisFieldDiff, ...]:
        if previous is None:
            return ()
        fields = set(previous) | set(current)
        return tuple(
            GenesisFieldDiff(
                field=field,
                before=previous.get(field),
                after=current.get(field),
            )
            for field in sorted(fields)
            if previous.get(field) != current.get(field)
        )

    def get_artifact_versions(
        self,
        conversation_id: UUID,
        principal: Principal,
    ) -> tuple[GenesisArtifactVersionView, ...]:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        return self._store.get_artifact_versions(
            organization_id=principal.organization_id,
            conversation_id=conversation_id,
        )
