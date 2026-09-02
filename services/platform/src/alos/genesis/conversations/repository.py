import json
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from alos.genesis.analysis.models import GenesisAnalyzeResult
from alos.genesis.conversations.models import (
    GenesisArtifactVersionView,
    GenesisConversationListItem,
    GenesisConversationStatus,
    GenesisConversationView,
    GenesisMessageView,
    GenesisSenderType,
)
from alos.genesis.models import GenesisFieldDiff


class GenesisConversationStore(Protocol):
    def create_conversation(
        self,
        organization_id: UUID,
        created_by_user_id: UUID,
        title: str,
        project_id: UUID | None = None,
        context_data: dict[str, Any] | None = None,
    ) -> GenesisConversationView: ...

    def list_conversations(
        self,
        organization_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[GenesisConversationListItem, ...]: ...

    def get_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> GenesisConversationView | None: ...

    def add_message(
        self,
        conversation_id: UUID,
        sender_type: GenesisSenderType,
        message_text: str,
        sender_user_id: UUID | None = None,
        analysis_result: GenesisAnalyzeResult | None = None,
        source_references: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> GenesisMessageView: ...

    def record_turn(
        self,
        conversation_id: UUID,
        user_id: UUID,
        user_message: str,
        assistant_message: str,
        analysis_result: GenesisAnalyzeResult,
        source_references: tuple[str, ...],
        diff: tuple[GenesisFieldDiff, ...],
    ) -> GenesisConversationView: ...

    def add_artifact_version(
        self,
        conversation_id: UUID,
        version_number: int,
        agent_id: str,
        spec_data: dict[str, Any],
        created_by_user_id: UUID,
        change_summary: str,
        diff: tuple[GenesisFieldDiff, ...] = (),
        metadata: dict[str, Any] | None = None,
        pipeline_request_id: UUID | None = None,
    ) -> GenesisArtifactVersionView: ...

    def get_artifact_versions(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> tuple[GenesisArtifactVersionView, ...]: ...

    def update_status(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        status: GenesisConversationStatus,
    ) -> None: ...


class InMemoryGenesisConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[UUID, GenesisConversationView] = {}
        self._messages: dict[UUID, list[GenesisMessageView]] = {}
        self._artifacts: dict[UUID, list[GenesisArtifactVersionView]] = {}

    def create_conversation(
        self,
        organization_id: UUID,
        created_by_user_id: UUID,
        title: str,
        project_id: UUID | None = None,
        context_data: dict[str, Any] | None = None,
    ) -> GenesisConversationView:
        conversation_id = uuid4()
        now = datetime.now(UTC)
        conv = GenesisConversationView(
            conversation_id=conversation_id,
            organization_id=organization_id,
            project_id=project_id,
            created_by_user_id=created_by_user_id,
            title=title,
            status=GenesisConversationStatus.ACTIVE,
            context_data=context_data or {},
            messages=(),
            artifact_versions=(),
            created_at=now,
            updated_at=now,
        )
        self._conversations[conversation_id] = conv
        self._messages[conversation_id] = []
        self._artifacts[conversation_id] = []
        return conv

    def list_conversations(
        self,
        organization_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[GenesisConversationListItem, ...]:
        items = [
            GenesisConversationListItem(
                conversation_id=c.conversation_id,
                organization_id=c.organization_id,
                project_id=c.project_id,
                created_by_user_id=c.created_by_user_id,
                title=c.title,
                status=c.status,
                message_count=len(self._messages.get(c.conversation_id, [])),
                artifact_version_count=len(self._artifacts.get(c.conversation_id, [])),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in self._conversations.values()
            if c.organization_id == organization_id
        ]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return tuple(items[offset : offset + limit])

    def get_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> GenesisConversationView | None:
        conv = self._conversations.get(conversation_id)
        if not conv or conv.organization_id != organization_id:
            return None
        messages = tuple(self._messages.get(conversation_id, []))
        artifacts = tuple(self._artifacts.get(conversation_id, []))
        return conv.model_copy(update={"messages": messages, "artifact_versions": artifacts})

    def add_message(
        self,
        conversation_id: UUID,
        sender_type: GenesisSenderType,
        message_text: str,
        sender_user_id: UUID | None = None,
        analysis_result: GenesisAnalyzeResult | None = None,
        source_references: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> GenesisMessageView:
        conv = self._conversations.get(conversation_id)
        if not conv:
            raise KeyError("Genesis conversation tidak ditemukan")
        now = datetime.now(UTC)
        msg = GenesisMessageView(
            message_id=uuid4(),
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            message_text=message_text,
            analysis_result=analysis_result,
            created_at=now,
            source_references=source_references,
            metadata=metadata or {},
        )
        self._messages[conversation_id].append(msg)
        self._conversations[conversation_id] = conv.model_copy(update={"updated_at": now})
        return msg

    def add_artifact_version(
        self,
        conversation_id: UUID,
        version_number: int,
        agent_id: str,
        spec_data: dict[str, Any],
        created_by_user_id: UUID,
        change_summary: str,
        diff: tuple[GenesisFieldDiff, ...] = (),
        metadata: dict[str, Any] | None = None,
        pipeline_request_id: UUID | None = None,
    ) -> GenesisArtifactVersionView:
        conv = self._conversations.get(conversation_id)
        if not conv:
            raise KeyError("Genesis conversation tidak ditemukan")
        now = datetime.now(UTC)
        artifact = GenesisArtifactVersionView(
            artifact_version_id=uuid4(),
            conversation_id=conversation_id,
            version_number=version_number,
            agent_id=agent_id,
            spec_data=spec_data,
            created_by_user_id=created_by_user_id,
            change_summary=change_summary,
            created_at=now,
            diff=tuple(diff),
            metadata=metadata or {},
            pipeline_request_id=pipeline_request_id,
        )
        self._artifacts[conversation_id].append(artifact)
        self._conversations[conversation_id] = conv.model_copy(update={"updated_at": now})
        return artifact

    def record_turn(
        self,
        conversation_id: UUID,
        user_id: UUID,
        user_message: str,
        assistant_message: str,
        analysis_result: GenesisAnalyzeResult,
        source_references: tuple[str, ...],
        diff: tuple[GenesisFieldDiff, ...],
    ) -> GenesisConversationView:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise KeyError("Genesis conversation tidak ditemukan")
        self.add_message(
            conversation_id,
            GenesisSenderType.USER,
            user_message,
            sender_user_id=user_id,
            source_references=source_references,
            metadata={"message_role": "REQUEST"},
        )
        self.add_message(
            conversation_id,
            GenesisSenderType.GENESIS_ASSISTANT,
            assistant_message,
            analysis_result=analysis_result,
            source_references=source_references,
            metadata=analysis_result.llm_metadata.model_dump(mode="json"),
        )
        version = len(self._artifacts.get(conversation_id, [])) + 1
        self.add_artifact_version(
            conversation_id,
            version_number=version,
            agent_id=analysis_result.agent_contract_draft.agent_id,
            spec_data=analysis_result.model_dump(mode="json"),
            created_by_user_id=user_id,
            change_summary=(
                f"Iterasi spesifikasi v{version}: {analysis_result.agent_contract_draft.name}"
            ),
            diff=diff,
            metadata={"source_references": list(source_references)},
        )
        result = self.get_conversation(conversation.organization_id, conversation_id)
        if result is None:
            raise KeyError("Genesis conversation tidak ditemukan")
        return result

    def get_artifact_versions(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> tuple[GenesisArtifactVersionView, ...]:
        conv = self.get_conversation(organization_id, conversation_id)
        if not conv:
            raise KeyError("Genesis conversation tidak ditemukan")
        return conv.artifact_versions

    def update_status(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        status: GenesisConversationStatus,
    ) -> None:
        conv = self._conversations.get(conversation_id)
        if not conv or conv.organization_id != organization_id:
            raise KeyError("Genesis conversation tidak ditemukan")
        self._conversations[conversation_id] = conv.model_copy(
            update={"status": status, "updated_at": datetime.now(UTC)}
        )


class PostgresGenesisConversationStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _conversation_organization(connection: Connection, conversation_id: UUID) -> UUID:
        row = connection.execute(
            text(
                """
                SELECT organization_id
                FROM genesis.conversations
                WHERE conversation_id = :conversation_id
                """
            ),
            {"conversation_id": conversation_id},
        ).fetchone()
        if row is None:
            raise KeyError("Genesis conversation tidak ditemukan")
        return cast(UUID, row.organization_id)

    def create_conversation(
        self,
        organization_id: UUID,
        created_by_user_id: UUID,
        title: str,
        project_id: UUID | None = None,
        context_data: dict[str, Any] | None = None,
    ) -> GenesisConversationView:
        conversation_id = uuid4()
        now = datetime.now(UTC)
        context_json = json.dumps(context_data or {}, ensure_ascii=False)
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.conversations (
                        conversation_id, organization_id, project_id,
                        created_by_user_id, title, status, context_data,
                        created_at, updated_at
                    ) VALUES (
                        :conversation_id, :organization_id, :project_id,
                        :created_by_user_id, :title, 'ACTIVE', CAST(:context_data AS jsonb),
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "conversation_id": conversation_id,
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "created_by_user_id": created_by_user_id,
                    "title": title,
                    "context_data": context_json,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return GenesisConversationView(
            conversation_id=conversation_id,
            organization_id=organization_id,
            project_id=project_id,
            created_by_user_id=created_by_user_id,
            title=title,
            status=GenesisConversationStatus.ACTIVE,
            context_data=context_data or {},
            messages=(),
            artifact_versions=(),
            created_at=now,
            updated_at=now,
        )

    def list_conversations(
        self,
        organization_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[GenesisConversationListItem, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        c.conversation_id,
                        c.organization_id,
                        c.project_id,
                        c.created_by_user_id,
                        c.title,
                        c.status,
                        c.created_at,
                        c.updated_at,
                        (
                            SELECT count(*) FROM genesis.messages m
                            WHERE m.conversation_id = c.conversation_id
                        ) AS message_count,
                        (
                            SELECT count(*) FROM genesis.artifact_versions a
                            WHERE a.conversation_id = c.conversation_id
                        ) AS artifact_version_count
                    FROM genesis.conversations c
                    WHERE c.organization_id = :org_id
                    ORDER BY c.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"org_id": organization_id, "limit": limit, "offset": offset},
            ).fetchall()

        return tuple(
            GenesisConversationListItem(
                conversation_id=row.conversation_id,
                organization_id=row.organization_id,
                project_id=row.project_id,
                created_by_user_id=row.created_by_user_id,
                title=row.title,
                status=GenesisConversationStatus(row.status),
                message_count=int(row.message_count),
                artifact_version_count=int(row.artifact_version_count),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        )

    def get_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> GenesisConversationView | None:
        with self._engine.connect() as connection:
            conv_row = connection.execute(
                text(
                    """
                    SELECT
                        conversation_id, organization_id, project_id,
                        created_by_user_id, title, status, context_data,
                        created_at, updated_at
                    FROM genesis.conversations
                    WHERE organization_id = :org_id AND conversation_id = :conv_id
                    """
                ),
                {"org_id": organization_id, "conv_id": conversation_id},
            ).fetchone()

            if not conv_row:
                return None

            msg_rows = connection.execute(
                text(
                    """
                    SELECT
                        message_id, conversation_id, sender_type,
                        sender_user_id, message_text, analysis_result, created_at,
                        source_references, metadata
                    FROM genesis.messages
                    WHERE conversation_id = :conv_id
                    ORDER BY created_at ASC
                    """
                ),
                {"conv_id": conversation_id},
            ).fetchall()

            art_rows = connection.execute(
                text(
                    """
                    SELECT
                        artifact_version_id, conversation_id, version_number,
                        agent_id, spec_data, created_by_user_id, change_summary, created_at,
                        diff_data, metadata, pipeline_request_id
                    FROM genesis.artifact_versions
                    WHERE conversation_id = :conv_id
                    ORDER BY version_number ASC
                    """
                ),
                {"conv_id": conversation_id},
            ).fetchall()

        messages = tuple(
            GenesisMessageView(
                message_id=row.message_id,
                conversation_id=row.conversation_id,
                sender_type=GenesisSenderType(row.sender_type),
                sender_user_id=row.sender_user_id,
                message_text=row.message_text,
                analysis_result=(
                    GenesisAnalyzeResult.model_validate(row.analysis_result)
                    if row.analysis_result
                    else None
                ),
                created_at=row.created_at,
                source_references=tuple(row.source_references or ()),
                metadata=dict(row.metadata or {}),
            )
            for row in msg_rows
        )

        artifacts = tuple(
            GenesisArtifactVersionView(
                artifact_version_id=row.artifact_version_id,
                conversation_id=row.conversation_id,
                version_number=int(row.version_number),
                agent_id=row.agent_id,
                spec_data=dict(row.spec_data or {}),
                created_by_user_id=row.created_by_user_id,
                change_summary=row.change_summary,
                created_at=row.created_at,
                diff=tuple(GenesisFieldDiff.model_validate(item) for item in (row.diff_data or ())),
                metadata=dict(row.metadata or {}),
                pipeline_request_id=row.pipeline_request_id,
            )
            for row in art_rows
        )

        return GenesisConversationView(
            conversation_id=conv_row.conversation_id,
            organization_id=conv_row.organization_id,
            project_id=conv_row.project_id,
            created_by_user_id=conv_row.created_by_user_id,
            title=conv_row.title,
            status=GenesisConversationStatus(conv_row.status),
            context_data=dict(conv_row.context_data or {}),
            messages=messages,
            artifact_versions=artifacts,
            created_at=conv_row.created_at,
            updated_at=conv_row.updated_at,
        )

    def add_message(
        self,
        conversation_id: UUID,
        sender_type: GenesisSenderType,
        message_text: str,
        sender_user_id: UUID | None = None,
        analysis_result: GenesisAnalyzeResult | None = None,
        source_references: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> GenesisMessageView:
        message_id = uuid4()
        now = datetime.now(UTC)
        analysis_json = (
            json.dumps(analysis_result.model_dump(mode="json"), ensure_ascii=False)
            if analysis_result
            else None
        )
        with self._engine.begin() as connection:
            organization_id = self._conversation_organization(connection, conversation_id)
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.messages (
                        message_id, conversation_id, organization_id, sender_type,
                        sender_user_id, message_text, analysis_result, created_at,
                        source_references, metadata, llm_provider, llm_model,
                        prompt_id, prompt_version, llm_result_status
                    ) VALUES (
                        :message_id, :conversation_id, :organization_id, :sender_type,
                        :sender_user_id, :message_text,
                        CAST(:analysis_result AS jsonb), :created_at,
                        CAST(:source_references AS jsonb), CAST(:metadata AS jsonb),
                        :llm_provider, :llm_model, :prompt_id, :prompt_version, :llm_result_status
                    )
                    """
                ),
                {
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "organization_id": organization_id,
                    "sender_type": sender_type.value,
                    "sender_user_id": sender_user_id,
                    "message_text": message_text,
                    "analysis_result": analysis_json,
                    "created_at": now,
                    "source_references": json.dumps(source_references),
                    "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                    "llm_provider": (
                        analysis_result.llm_metadata.provider if analysis_result else None
                    ),
                    "llm_model": analysis_result.llm_metadata.model if analysis_result else None,
                    "prompt_id": analysis_result.llm_metadata.prompt_id
                    if analysis_result
                    else None,
                    "prompt_version": (
                        analysis_result.llm_metadata.prompt_version if analysis_result else None
                    ),
                    "llm_result_status": (
                        analysis_result.llm_result_status if analysis_result else None
                    ),
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE genesis.conversations
                    SET updated_at = :updated_at
                    WHERE conversation_id = :conv_id
                    """
                ),
                {"updated_at": now, "conv_id": conversation_id},
            )

        return GenesisMessageView(
            message_id=message_id,
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            message_text=message_text,
            analysis_result=analysis_result,
            created_at=now,
            source_references=source_references,
            metadata=metadata or {},
        )

    def add_artifact_version(
        self,
        conversation_id: UUID,
        version_number: int,
        agent_id: str,
        spec_data: dict[str, Any],
        created_by_user_id: UUID,
        change_summary: str,
        diff: tuple[GenesisFieldDiff, ...] = (),
        metadata: dict[str, Any] | None = None,
        pipeline_request_id: UUID | None = None,
    ) -> GenesisArtifactVersionView:
        artifact_id = uuid4()
        now = datetime.now(UTC)
        spec_json = json.dumps(spec_data, ensure_ascii=False)
        with self._engine.begin() as connection:
            organization_id = self._conversation_organization(connection, conversation_id)
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.artifact_versions (
                        artifact_version_id, conversation_id, organization_id, version_number,
                        agent_id, spec_data, created_by_user_id, change_summary, created_at,
                        diff_data, metadata, pipeline_request_id
                    ) VALUES (
                        :artifact_version_id, :conversation_id, :organization_id, :version_number,
                        :agent_id, CAST(:spec_data AS jsonb), :created_by_user_id,
                        :change_summary, :created_at, CAST(:diff_data AS jsonb),
                        CAST(:metadata AS jsonb), :pipeline_request_id
                    )
                    """
                ),
                {
                    "artifact_version_id": artifact_id,
                    "conversation_id": conversation_id,
                    "organization_id": organization_id,
                    "version_number": version_number,
                    "agent_id": agent_id,
                    "spec_data": spec_json,
                    "created_by_user_id": created_by_user_id,
                    "change_summary": change_summary,
                    "created_at": now,
                    "diff_data": json.dumps(
                        [
                            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                            for item in diff
                        ]
                    ),
                    "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                    "pipeline_request_id": pipeline_request_id,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE genesis.conversations
                    SET updated_at = :updated_at
                    WHERE conversation_id = :conv_id
                    """
                ),
                {"updated_at": now, "conv_id": conversation_id},
            )

        return GenesisArtifactVersionView(
            artifact_version_id=artifact_id,
            conversation_id=conversation_id,
            version_number=version_number,
            agent_id=agent_id,
            spec_data=spec_data,
            created_by_user_id=created_by_user_id,
            change_summary=change_summary,
            created_at=now,
            diff=tuple(diff),
            metadata=metadata or {},
            pipeline_request_id=pipeline_request_id,
        )

    def record_turn(
        self,
        conversation_id: UUID,
        user_id: UUID,
        user_message: str,
        assistant_message: str,
        analysis_result: GenesisAnalyzeResult,
        source_references: tuple[str, ...],
        diff: tuple[GenesisFieldDiff, ...],
    ) -> GenesisConversationView:
        """Persist one complete conversation turn in a single transaction."""

        user_message_id = uuid4()
        assistant_message_id = uuid4()
        artifact_id = uuid4()
        now = datetime.now(UTC)
        analysis_json = json.dumps(analysis_result.model_dump(mode="json"), ensure_ascii=False)
        metadata_json = json.dumps(
            analysis_result.llm_metadata.model_dump(mode="json"), ensure_ascii=False
        )
        diff_json = json.dumps(
            [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in diff
            ],
            ensure_ascii=False,
        )
        spec_json = analysis_json

        with self._engine.begin() as connection:
            conversation = connection.execute(
                text(
                    """
                    SELECT organization_id
                    FROM genesis.conversations
                    WHERE conversation_id = :conversation_id
                    FOR UPDATE
                    """
                ),
                {"conversation_id": conversation_id},
            ).fetchone()
            if conversation is None:
                raise KeyError("Genesis conversation tidak ditemukan")
            organization_id = conversation.organization_id

            version_row = connection.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version
                    FROM genesis.artifact_versions
                    WHERE conversation_id = :conversation_id
                    """
                ),
                {"conversation_id": conversation_id},
            ).one()
            version_number = int(version_row.next_version)

            connection.execute(
                text(
                    """
                    INSERT INTO genesis.messages (
                        message_id, conversation_id, organization_id, sender_type, sender_user_id,
                        message_text, analysis_result, created_at, source_references,
                        metadata, llm_provider, llm_model, prompt_id, prompt_version,
                        llm_result_status
                    ) VALUES (
                        :message_id, :conversation_id, :organization_id, 'USER', :sender_user_id,
                        :message_text, NULL, :created_at, CAST(:source_references AS jsonb),
                        CAST(:metadata AS jsonb), NULL, NULL, NULL, NULL, NULL
                    )
                    """
                ),
                {
                    "message_id": user_message_id,
                    "conversation_id": conversation_id,
                    "organization_id": organization_id,
                    "sender_user_id": user_id,
                    "message_text": user_message,
                    "created_at": now,
                    "source_references": json.dumps(source_references),
                    "metadata": json.dumps({"message_role": "REQUEST"}),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.messages (
                        message_id, conversation_id, organization_id, sender_type, sender_user_id,
                        message_text, analysis_result, created_at, source_references,
                        metadata, llm_provider, llm_model, prompt_id, prompt_version,
                        llm_result_status
                    ) VALUES (
                        :message_id, :conversation_id, :organization_id, 'GENESIS_ASSISTANT', NULL,
                        :message_text, CAST(:analysis_result AS jsonb), :created_at,
                        CAST(:source_references AS jsonb), CAST(:metadata AS jsonb),
                        :llm_provider, :llm_model, :prompt_id, :prompt_version,
                        :llm_result_status
                    )
                    """
                ),
                {
                    "message_id": assistant_message_id,
                    "conversation_id": conversation_id,
                    "organization_id": organization_id,
                    "message_text": assistant_message,
                    "analysis_result": analysis_json,
                    "created_at": now,
                    "source_references": json.dumps(source_references),
                    "metadata": metadata_json,
                    "llm_provider": analysis_result.llm_metadata.provider,
                    "llm_model": analysis_result.llm_metadata.model,
                    "prompt_id": analysis_result.llm_metadata.prompt_id,
                    "prompt_version": analysis_result.llm_metadata.prompt_version,
                    "llm_result_status": analysis_result.llm_result_status,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.artifact_versions (
                        artifact_version_id, conversation_id, organization_id,
                        version_number, agent_id,
                        spec_data, created_by_user_id, change_summary, created_at,
                        diff_data, metadata, pipeline_request_id
                    ) VALUES (
                        :artifact_id, :conversation_id, :organization_id,
                        :version_number, :agent_id,
                        CAST(:spec_data AS jsonb), :created_by_user_id, :change_summary,
                        :created_at, CAST(:diff_data AS jsonb), CAST(:metadata AS jsonb), NULL
                    )
                    """
                ),
                {
                    "artifact_id": artifact_id,
                    "conversation_id": conversation_id,
                    "organization_id": organization_id,
                    "version_number": version_number,
                    "agent_id": analysis_result.agent_contract_draft.agent_id,
                    "spec_data": spec_json,
                    "created_by_user_id": user_id,
                    "change_summary": (
                        f"Iterasi spesifikasi v{version_number}: "
                        f"{analysis_result.agent_contract_draft.name}"
                    ),
                    "created_at": now,
                    "diff_data": diff_json,
                    "metadata": json.dumps(
                        {"source_references": list(source_references)},
                        ensure_ascii=False,
                    ),
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE genesis.conversations
                    SET updated_at = :updated_at
                    WHERE conversation_id = :conversation_id
                    """
                ),
                {"updated_at": now, "conversation_id": conversation_id},
            )

        result = self.get_conversation(conversation.organization_id, conversation_id)
        if result is None:
            raise KeyError("Genesis conversation tidak ditemukan")
        return result

    def get_artifact_versions(
        self,
        organization_id: UUID,
        conversation_id: UUID,
    ) -> tuple[GenesisArtifactVersionView, ...]:
        conv = self.get_conversation(organization_id, conversation_id)
        if not conv:
            raise KeyError("Genesis conversation tidak ditemukan")
        return conv.artifact_versions

    def update_status(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        status: GenesisConversationStatus,
    ) -> None:
        with self._engine.begin() as connection:
            res = connection.execute(
                text(
                    """
                    UPDATE genesis.conversations
                    SET status = :status, updated_at = :updated_at
                    WHERE organization_id = :org_id AND conversation_id = :conv_id
                    """
                ),
                {
                    "status": status.value,
                    "updated_at": datetime.now(UTC),
                    "org_id": organization_id,
                    "conv_id": conversation_id,
                },
            )
            if res.rowcount == 0:
                raise KeyError("Genesis conversation tidak ditemukan")
