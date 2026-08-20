import importlib
import json
from datetime import datetime
from typing import Any

from .schemas import AssetOutput, CampaignBrief, CampaignRecord, TaskRecord, ValidationResult

try:
    psycopg = importlib.import_module("psycopg")
except ModuleNotFoundError:
    psycopg = None


class PostgresPersistence:
    def __init__(self, dsn: str):
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgresPersistence")
        self._dsn = dsn

    def _connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgresPersistence")
        return psycopg.connect(self._dsn)

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaigns (
                        campaign_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        brief_json JSONB NOT NULL,
                        deleted_at TIMESTAMP
                    );
                    """
                )
                cur.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;")
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_campaigns_company_created
                    ON campaigns (company_id, created_at DESC) WHERE deleted_at IS NULL;
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_tasks (
                        task_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        company_id TEXT NOT NULL,
                        task_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        priority INTEGER NOT NULL,
                        depends_on_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        acceptance_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_campaign_tasks_campaign_priority
                    ON campaign_tasks (campaign_id, priority ASC, created_at ASC);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_runs (
                        run_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        company_id TEXT NOT NULL DEFAULT '',
                        run_number INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        rerun_mode TEXT NOT NULL DEFAULT 'regenerate_all',
                        started_at TIMESTAMP NOT NULL,
                        completed_at TIMESTAMP,
                        triggered_by TEXT NOT NULL DEFAULT 'system',
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        UNIQUE (campaign_id, run_number)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_campaign_runs_campaign_started
                    ON campaign_runs (campaign_id, started_at DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS asset_outputs (
                        asset_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL DEFAULT '',
                        campaign_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        asset_type TEXT NOT NULL,
                        url TEXT NOT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        validation_status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute("ALTER TABLE asset_outputs ADD COLUMN IF NOT EXISTS company_id TEXT NOT NULL DEFAULT '';")
                cur.execute("ALTER TABLE asset_outputs ADD COLUMN IF NOT EXISTS run_id TEXT;")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS validation_results (
                        validation_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL DEFAULT '',
                        campaign_id TEXT NOT NULL,
                        asset_id TEXT NOT NULL,
                        validator TEXT NOT NULL,
                        score NUMERIC(5,4) NOT NULL,
                        result TEXT NOT NULL,
                        reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS company_id TEXT NOT NULL DEFAULT '';")
                cur.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS run_id TEXT;")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_items (
                        review_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        company_id TEXT NOT NULL DEFAULT '',
                        run_id TEXT,
                        asset_id TEXT NOT NULL,
                        validation_id TEXT,
                        asset_type TEXT NOT NULL DEFAULT 'unknown',
                        score NUMERIC(5,4) NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'review_pending',
                        source TEXT NOT NULL DEFAULT 'ai',
                        assignee TEXT,
                        reason TEXT,
                        submitted_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_review_items_campaign_status
                    ON review_items (campaign_id, status, submitted_at DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS asset_versions (
                        version_id TEXT PRIMARY KEY,
                        asset_id TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        version_number INTEGER NOT NULL,
                        url TEXT NOT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        UNIQUE (asset_id, run_id)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_asset_versions_asset_created
                    ON asset_versions (asset_id, version_number DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_references (
                        reference_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        file_size BIGINT NOT NULL,
                        uploaded_at TIMESTAMP NOT NULL,
                        stored_path TEXT NOT NULL,
                        operator TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    "ALTER TABLE campaign_references ADD COLUMN IF NOT EXISTS folder TEXT NOT NULL DEFAULT 'General';"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_items (
                        item_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        source TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        content_url TEXT,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        deleted_at TIMESTAMP
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_templates (
                        template_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        active_version INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'active',
                        versions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute("ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';")
                cur.execute("ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS versions_json JSONB NOT NULL DEFAULT '[]'::jsonb;")
                cur.execute("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS content_url TEXT;")
                cur.execute("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
                cur.execute("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;")
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_knowledge_items_company_created
                    ON knowledge_items (company_id, created_at DESC) WHERE deleted_at IS NULL;
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chatbot_audit_logs (
                        audit_id TEXT PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL,
                        actor_id TEXT NOT NULL,
                        actor_role TEXT NOT NULL,
                        locale TEXT NOT NULL,
                        message TEXT NOT NULL,
                        intent TEXT NOT NULL,
                        ok BOOLEAN NOT NULL,
                        detail TEXT,
                        request_pending_action_type TEXT,
                        request_pending_campaign_id TEXT,
                        request_pending_reference_id TEXT,
                        request_pending_review_id TEXT,
                        result_pending_action_type TEXT,
                        result_pending_campaign_id TEXT,
                        result_pending_reference_id TEXT,
                        result_pending_review_id TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_traces (
                        trace_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL UNIQUE,
                        created_by TEXT NOT NULL,
                        source TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_trace_events (
                        event_id TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        campaign_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        actor_role TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP NOT NULL,
                        company_id TEXT NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS campaign_chat_transcripts (
                        message_id TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        campaign_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content_masked TEXT NOT NULL,
                        raw_ref TEXT,
                        created_at TIMESTAMP NOT NULL,
                        company_id TEXT NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_trace_events_campaign_created
                    ON campaign_trace_events (campaign_id, created_at DESC, event_id DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_trace_events_campaign_type_created
                    ON campaign_trace_events (campaign_id, event_type, created_at DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_trace_chat_campaign_created
                    ON campaign_chat_transcripts (campaign_id, created_at DESC, message_id DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_trace_events_created_at
                    ON campaign_trace_events (created_at DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_trace_chat_created_at
                    ON campaign_chat_transcripts (created_at DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS work_orders (
                        work_order_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        task_id TEXT,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        assignee TEXT,
                        status TEXT NOT NULL,
                        priority INTEGER NOT NULL,
                        created_by TEXT NOT NULL,
                        due_at TIMESTAMP,
                        escalated_at TIMESTAMP,
                        escalation_reason TEXT,
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL
                    );
                    """
                )
                cur.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS due_at TIMESTAMP;")
                cur.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMP;")
                cur.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS escalation_reason TEXT;")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS work_order_messages (
                        message_id TEXT PRIMARY KEY,
                        work_order_id TEXT NOT NULL,
                        campaign_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content_masked TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_work_orders_campaign_updated
                    ON work_orders (campaign_id, updated_at DESC, work_order_id DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_work_order_messages_order_created
                    ON work_order_messages (work_order_id, created_at DESC, message_id DESC);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                        sub_id TEXT PRIMARY KEY,
                        company_id TEXT NOT NULL DEFAULT '',
                        url TEXT NOT NULL,
                        secret TEXT NOT NULL DEFAULT '',
                        events JSONB NOT NULL DEFAULT '[]'::jsonb,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_company
                    ON webhook_subscriptions (company_id, active);
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS webhook_delivery_log (
                        log_id TEXT PRIMARY KEY,
                        sub_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        response_code INTEGER,
                        response_body TEXT,
                        attempt INTEGER NOT NULL DEFAULT 1,
                        delivered_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        next_retry_at TIMESTAMP,
                        status TEXT NOT NULL DEFAULT 'delivered'
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_webhook_delivery_sub_created
                    ON webhook_delivery_log (sub_id, delivered_at DESC);
                    """
                )
                self.initialize_llm_tables()
            conn.commit()

    def create_campaign(self, campaign: CampaignRecord) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO campaigns (campaign_id, company_id, status, created_at, brief_json, deleted_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, NULL)
                    ON CONFLICT (campaign_id) DO UPDATE SET
                        company_id = EXCLUDED.company_id,
                        status = EXCLUDED.status,
                        brief_json = EXCLUDED.brief_json,
                        deleted_at = NULL;
                    """,
                    (
                        campaign.campaign_id,
                        campaign.company_id,
                        campaign.status,
                        campaign.created_at,
                        json.dumps(campaign.brief.model_dump(mode="json")),
                    ),
                )
            conn.commit()

    def get_campaign(self, campaign_id: str) -> CampaignRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT campaign_id, company_id, status, created_at, brief_json, deleted_at
                    FROM campaigns
                    WHERE campaign_id = %s AND deleted_at IS NULL;
                    """,
                    (campaign_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return CampaignRecord(
            campaign_id=row[0],
            company_id=row[1],
            status=row[2],
            created_at=row[3],
            brief=CampaignBrief(**row[4]),
            deleted_at=row[5],
        )

    def list_campaigns(self, company_id: str | None = None) -> list[CampaignRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if company_id is None:
                    cur.execute(
                        """
                        SELECT campaign_id, company_id, status, created_at, brief_json, deleted_at
                        FROM campaigns
                        WHERE deleted_at IS NULL
                        ORDER BY created_at DESC;
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT campaign_id, company_id, status, created_at, brief_json, deleted_at
                        FROM campaigns
                        WHERE company_id = %s AND deleted_at IS NULL
                        ORDER BY created_at DESC;
                        """,
                        (company_id,),
                    )
                rows = cur.fetchall()
        return [
            CampaignRecord(
                campaign_id=row[0],
                company_id=row[1],
                status=row[2],
                created_at=row[3],
                brief=CampaignBrief(**row[4]),
                deleted_at=row[5],
            )
            for row in rows
        ]

    def set_campaign_status(self, campaign_id: str, status: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE campaigns SET status = %s WHERE campaign_id = %s", (status, campaign_id))
            conn.commit()

    def update_campaign_brief(self, campaign_id: str, brief: CampaignBrief) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE campaigns SET brief_json = %s::jsonb WHERE campaign_id = %s AND deleted_at IS NULL",
                    (json.dumps(brief.model_dump(mode="json")), campaign_id),
                )
            conn.commit()

    def delete_campaign(self, campaign_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE campaigns SET deleted_at = %s WHERE campaign_id = %s AND deleted_at IS NULL",
                    (datetime.utcnow(), campaign_id),
                )
            conn.commit()

    def set_tasks(self, campaign_id: str, tasks: list[TaskRecord]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM campaign_tasks WHERE campaign_id = %s", (campaign_id,))
                for item in tasks:
                    cur.execute(
                        """
                        INSERT INTO campaign_tasks
                            (task_id, campaign_id, company_id, task_type, status, priority, depends_on_json, acceptance_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                        """,
                        (
                            item.task_id,
                            item.campaign_id,
                            item.company_id,
                            item.task_type,
                            item.status,
                            item.priority,
                            json.dumps(item.depends_on),
                            json.dumps(item.acceptance),
                        ),
                    )
            conn.commit()

    def get_tasks(self, campaign_id: str) -> list[TaskRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, campaign_id, company_id, task_type, status, priority, depends_on_json, acceptance_json
                    FROM campaign_tasks
                    WHERE campaign_id = %s
                    ORDER BY priority ASC, created_at ASC;
                    """,
                    (campaign_id,),
                )
                rows = cur.fetchall()
        return [
            TaskRecord(
                task_id=row[0],
                campaign_id=row[1],
                company_id=row[2],
                task_type=row[3],
                status=row[4],
                priority=row[5],
                depends_on=list(row[6] or []),
                acceptance=list(row[7] or []),
            )
            for row in rows
        ]

    def create_campaign_run(
        self,
        run_id: str,
        campaign_id: str,
        company_id: str,
        status: str,
        triggered_by: str,
        rerun_mode: str = "regenerate_all",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        started_at = datetime.utcnow()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(run_number), 0) + 1 FROM campaign_runs WHERE campaign_id = %s", (campaign_id,))
                run_number = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO campaign_runs
                        (run_id, campaign_id, company_id, run_number, status, rerun_mode, started_at, triggered_by, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (run_id) DO NOTHING;
                    """,
                    (run_id, campaign_id, company_id, run_number, status, rerun_mode, started_at, triggered_by, json.dumps(metadata or {})),
                )
            conn.commit()
        return run_number

    def complete_campaign_run(self, run_id: str, status: str, metadata: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if metadata is None:
                    cur.execute(
                        "UPDATE campaign_runs SET status = %s, completed_at = %s WHERE run_id = %s",
                        (status, datetime.utcnow(), run_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE campaign_runs
                        SET status = %s, completed_at = %s, metadata_json = metadata_json || %s::jsonb
                        WHERE run_id = %s
                        """,
                        (status, datetime.utcnow(), json.dumps(metadata), run_id),
                    )
            conn.commit()

    def get_latest_campaign_run(self, campaign_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, campaign_id, company_id, run_number, status, rerun_mode, started_at, completed_at, triggered_by, metadata_json
                    FROM campaign_runs
                    WHERE campaign_id = %s
                    ORDER BY run_number DESC
                    LIMIT 1;
                    """,
                    (campaign_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "campaign_id": row[1],
            "company_id": row[2],
            "run_number": int(row[3]),
            "status": row[4],
            "rerun_mode": row[5],
            "started_at": row[6],
            "completed_at": row[7],
            "triggered_by": row[8],
            "metadata": row[9] or {},
        }

    def list_campaign_runs(self, campaign_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, campaign_id, company_id, run_number, status, rerun_mode, started_at, completed_at, triggered_by, metadata_json
                    FROM campaign_runs
                    WHERE campaign_id = %s
                    ORDER BY run_number DESC;
                    """,
                    (campaign_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "run_id": row[0],
                "campaign_id": row[1],
                "company_id": row[2],
                "run_number": int(row[3]),
                "status": row[4],
                "rerun_mode": row[5],
                "started_at": row[6],
                "completed_at": row[7],
                "triggered_by": row[8],
                "metadata": row[9] or {},
            }
            for row in rows
        ]

    def save_asset_version(self, version_id: str, asset_id: str, run_id: str, version_number: int, url: str, metadata: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO asset_versions (version_id, asset_id, run_id, version_number, url, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (asset_id, run_id) DO UPDATE SET
                        version_id = EXCLUDED.version_id,
                        version_number = EXCLUDED.version_number,
                        url = EXCLUDED.url,
                        metadata_json = EXCLUDED.metadata_json;
                    """,
                    (version_id, asset_id, run_id, version_number, url, json.dumps(metadata or {})),
                )
            conn.commit()

    def list_asset_versions(self, asset_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT version_id, asset_id, run_id, version_number, url, metadata_json, created_at
                    FROM asset_versions
                    WHERE asset_id = %s
                    ORDER BY version_number DESC;
                    """,
                    (asset_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "version_id": row[0],
                "asset_id": row[1],
                "run_id": row[2],
                "version_number": int(row[3]),
                "url": row[4],
                "metadata": row[5] or {},
                "created_at": row[6],
            }
            for row in rows
        ]

    def save_asset_outputs(self, assets: list[AssetOutput]) -> None:
        if not assets:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                for item in assets:
                    cur.execute(
                        """
                        INSERT INTO asset_outputs
                            (asset_id, company_id, campaign_id, task_id, asset_type, url, metadata_json, validation_status, created_at, run_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                        ON CONFLICT (asset_id) DO UPDATE SET
                            company_id = EXCLUDED.company_id,
                            run_id = EXCLUDED.run_id,
                            metadata_json = EXCLUDED.metadata_json,
                            validation_status = EXCLUDED.validation_status,
                            url = EXCLUDED.url;
                        """,
                        (
                            item.asset_id,
                            item.company_id,
                            item.campaign_id,
                            item.task_id,
                            item.asset_type,
                            item.url,
                            json.dumps(item.metadata),
                            item.validation_status,
                            item.created_at,
                            item.run_id,
                        ),
                    )
            conn.commit()

    def save_validation_results(self, results: list[ValidationResult]) -> None:
        if not results:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                for item in results:
                    cur.execute(
                        """
                        INSERT INTO validation_results
                            (validation_id, company_id, campaign_id, asset_id, validator, score, result, reasons_json, created_at, run_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                        ON CONFLICT (validation_id) DO UPDATE SET
                            company_id = EXCLUDED.company_id,
                            run_id = EXCLUDED.run_id,
                            score = EXCLUDED.score,
                            result = EXCLUDED.result,
                            reasons_json = EXCLUDED.reasons_json;
                        """,
                        (
                            item.validation_id,
                            item.company_id,
                            item.campaign_id,
                            item.asset_id,
                            item.validator,
                            item.score,
                            item.result,
                            json.dumps(item.reasons),
                            item.created_at,
                            item.run_id,
                        ),
                    )
            conn.commit()

    def list_asset_outputs(self, campaign_id: str) -> list[AssetOutput]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT asset_id, company_id, campaign_id, task_id, asset_type, url, metadata_json, validation_status, created_at, run_id
                    FROM asset_outputs
                    WHERE campaign_id = %s
                    ORDER BY created_at DESC;
                    """,
                    (campaign_id,),
                )
                rows = cur.fetchall()

        assets: list[AssetOutput] = []
        for row in rows:
            assets.append(
                AssetOutput(
                    asset_id=row[0],
                    company_id=row[1],
                    campaign_id=row[2],
                    task_id=row[3],
                    asset_type=row[4],
                    url=row[5],
                    metadata=row[6],
                    validation_status=row[7],
                    created_at=row[8],
                    run_id=row[9],
                )
            )
        return assets

    def get_asset_output(self, asset_id: str) -> AssetOutput | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT asset_id, company_id, campaign_id, task_id, asset_type, url, metadata_json, validation_status, created_at, run_id
                    FROM asset_outputs
                    WHERE asset_id = %s
                    LIMIT 1;
                    """,
                    (asset_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return AssetOutput(
            asset_id=row[0],
            company_id=row[1],
            campaign_id=row[2],
            task_id=row[3],
            asset_type=row[4],
            url=row[5],
            metadata=row[6],
            validation_status=row[7],
            created_at=row[8],
            run_id=row[9],
        )

    def update_asset_validation_status(self, asset_id: str, validation_status: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE asset_outputs SET validation_status = %s WHERE asset_id = %s",
                    (validation_status, asset_id),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return changed

    def list_validation_results(self, campaign_id: str) -> list[ValidationResult]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT validation_id, company_id, campaign_id, asset_id, validator, score, result, reasons_json, created_at, run_id
                    FROM validation_results
                    WHERE campaign_id = %s
                    ORDER BY created_at DESC;
                    """,
                    (campaign_id,),
                )
                rows = cur.fetchall()

        results: list[ValidationResult] = []
        for row in rows:
            results.append(
                ValidationResult(
                    validation_id=row[0],
                    company_id=row[1],
                    campaign_id=row[2],
                    asset_id=row[3],
                    validator=row[4],
                    score=float(row[5]),
                    result=row[6],
                    reasons=row[7],
                    created_at=row[8],
                    run_id=row[9],
                )
            )
        return results

    def upsert_review_items_for_validations(self, assets: list[AssetOutput], validations: list[ValidationResult]) -> None:
        if not assets or not validations:
            return
        asset_map = {asset.asset_id: asset for asset in assets}
        with self._connect() as conn:
            with conn.cursor() as cur:
                for validation in validations:
                    asset = asset_map.get(validation.asset_id)
                    if asset is None:
                        continue
                    review_id = f"rev_{validation.validation_id}"
                    source = "manual" if (asset.metadata or {}).get("source") in {"manual", "manual_upload"} else "ai"
                    cur.execute(
                        """
                        INSERT INTO review_items
                            (review_id, campaign_id, company_id, run_id, asset_id, validation_id, asset_type, score, status, source, submitted_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'review_pending', %s, %s)
                        ON CONFLICT (review_id) DO UPDATE SET
                            score = EXCLUDED.score,
                            run_id = EXCLUDED.run_id,
                            asset_type = EXCLUDED.asset_type,
                            source = EXCLUDED.source,
                            updated_at = NOW();
                        """,
                        (
                            review_id,
                            validation.campaign_id,
                            validation.company_id,
                            validation.run_id or asset.run_id,
                            validation.asset_id,
                            validation.validation_id,
                            asset.asset_type,
                            validation.score,
                            source,
                            validation.created_at,
                        ),
                    )
            conn.commit()

    def list_review_items(self, status: str | None = None, campaign_id: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if status:
            where.append("r.status = %s")
            params.append(status)
        if campaign_id:
            where.append("r.campaign_id = %s")
            params.append(campaign_id)
        if run_id:
            where.append("r.run_id = %s")
            params.append(run_id)
        clause = "WHERE " + " AND ".join(where) if where else ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT r.review_id, r.campaign_id, r.asset_id, r.score, r.status, r.submitted_at, r.assignee, r.run_id, r.asset_type, r.source, r.reason, a.metadata_json
                    FROM review_items r
                    LEFT JOIN asset_outputs a ON a.asset_id = r.asset_id
                    {clause}
                    ORDER BY r.submitted_at DESC;
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return [
            {
                "review_id": row[0],
                "campaign_id": row[1],
                "asset_id": row[2],
                "score": float(row[3]),
                "status": row[4],
                "submitted_at": row[5],
                "assignee": row[6],
                "run_id": row[7],
                "asset_type": row[8],
                "source": row[9],
                "reason": row[10],
                "metadata": row[11] or {},
            }
            for row in rows
        ]

    def get_review_item_by_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.review_id, r.campaign_id, r.asset_id, r.score, r.status, r.submitted_at, r.assignee, r.run_id, r.asset_type, r.source, r.reason, a.metadata_json
                    FROM review_items r
                    LEFT JOIN asset_outputs a ON a.asset_id = r.asset_id
                    WHERE r.asset_id = %s
                    ORDER BY r.submitted_at DESC
                    LIMIT 1;
                    """,
                    (asset_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "review_id": row[0],
            "campaign_id": row[1],
            "asset_id": row[2],
            "score": float(row[3]),
            "status": row[4],
            "submitted_at": row[5],
            "assignee": row[6],
            "run_id": row[7],
            "asset_type": row[8],
            "source": row[9],
            "reason": row[10],
            "metadata": row[11] or {},
        }

    def update_review_item_status(self, review_id: str, status: str, operator: str, reason: str | None = None) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE review_items
                    SET status = %s, assignee = %s, reason = %s, updated_at = NOW()
                    WHERE review_id = %s
                    """,
                    (status, operator, reason, review_id),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return changed

    def backfill_review_items(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO review_items
                        (review_id, campaign_id, company_id, run_id, asset_id, validation_id, asset_type, score, status, source, submitted_at)
                    SELECT
                        'rev_' || v.validation_id,
                        v.campaign_id,
                        v.company_id,
                        COALESCE(v.run_id, a.run_id),
                        v.asset_id,
                        v.validation_id,
                        a.asset_type,
                        v.score,
                        'review_pending',
                        CASE WHEN COALESCE(a.metadata_json->>'source', '') IN ('manual', 'manual_upload') THEN 'manual' ELSE 'ai' END,
                        v.created_at
                    FROM validation_results v
                    JOIN asset_outputs a ON a.asset_id = v.asset_id
                    ON CONFLICT (review_id) DO NOTHING;
                    """
                )
                changed = cur.rowcount
            conn.commit()
        return int(changed or 0)

    def delete_generated_assets_except(self, campaign_id: str, keep_asset_ids: set[str]) -> int:
        """Delete non-manual generated assets not included in the current visible bundle.

        Manual assets are identified by metadata_json.source = 'manual' and are never removed.
        Validation rows and review_items for removed assets are removed at the same time.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                if keep_asset_ids:
                    cur.execute(
                        """
                        WITH deleted AS (
                            DELETE FROM asset_outputs
                            WHERE campaign_id = %s
                              AND COALESCE(metadata_json->>'source', '') <> 'manual'
                              AND NOT (metadata_json ? 'asset_base_name')
                              AND NOT (asset_id = ANY(%s))
                            RETURNING asset_id
                        ), deleted_validations AS (
                            DELETE FROM validation_results
                            WHERE asset_id IN (SELECT asset_id FROM deleted)
                            RETURNING validation_id
                        ), deleted_reviews AS (
                            DELETE FROM review_items
                            WHERE campaign_id = %s
                              AND asset_id IN (SELECT asset_id FROM deleted)
                            RETURNING review_id
                        )
                        SELECT COUNT(*) FROM deleted;
                        """,
                        (campaign_id, list(keep_asset_ids), campaign_id),
                    )
                else:
                    cur.execute(
                        """
                        WITH deleted AS (
                            DELETE FROM asset_outputs
                            WHERE campaign_id = %s
                              AND COALESCE(metadata_json->>'source', '') <> 'manual'
                              AND NOT (metadata_json ? 'asset_base_name')
                            RETURNING asset_id
                        ), deleted_validations AS (
                            DELETE FROM validation_results
                            WHERE asset_id IN (SELECT asset_id FROM deleted)
                            RETURNING validation_id
                        ), deleted_reviews AS (
                            DELETE FROM review_items
                            WHERE campaign_id = %s
                              AND asset_id IN (SELECT asset_id FROM deleted)
                            RETURNING review_id
                        )
                        SELECT COUNT(*) FROM deleted;
                        """,
                        (campaign_id, campaign_id),
                    )
                deleted_count = int(cur.fetchone()[0])
            conn.commit()
        return deleted_count

    def save_campaign_reference(
        self,
        reference_id: str,
        campaign_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        uploaded_at: datetime,
        stored_path: str,
        operator: str | None,
        folder: str = "General",
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO campaign_references
                        (reference_id, campaign_id, file_name, file_type, file_size, uploaded_at, stored_path, operator, folder)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (reference_id) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_type = EXCLUDED.file_type,
                        file_size = EXCLUDED.file_size,
                        uploaded_at = EXCLUDED.uploaded_at,
                        stored_path = EXCLUDED.stored_path,
                        operator = EXCLUDED.operator,
                        folder = EXCLUDED.folder;
                    """,
                    (
                        reference_id,
                        campaign_id,
                        file_name,
                        file_type,
                        file_size,
                        uploaded_at,
                        stored_path,
                        operator,
                        folder,
                    ),
                )
            conn.commit()

    def list_campaign_references(self, campaign_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT reference_id, campaign_id, file_name, file_type, file_size, uploaded_at, stored_path, folder
                    FROM campaign_references
                    WHERE campaign_id = %s
                    ORDER BY uploaded_at DESC;
                    """,
                    (campaign_id,),
                )
                rows = cur.fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "reference_id": row[0],
                    "campaign_id": row[1],
                    "file_name": row[2],
                    "file_type": row[3],
                    "file_size": int(row[4]),
                    "uploaded_at": row[5],
                    "stored_path": row[6],
                    "folder": row[7] or "General",
                }
            )
        return items

    def get_campaign_reference(self, campaign_id: str, reference_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT reference_id, campaign_id, file_name, file_type, file_size, uploaded_at, stored_path, folder
                    FROM campaign_references
                    WHERE campaign_id = %s AND reference_id = %s
                    LIMIT 1;
                    """,
                    (campaign_id, reference_id),
                )
                row = cur.fetchone()

        if row is None:
            return None

        return {
            "reference_id": row[0],
            "campaign_id": row[1],
            "file_name": row[2],
            "file_type": row[3],
            "file_size": int(row[4]),
            "uploaded_at": row[5],
            "stored_path": row[6],
            "folder": row[7] or "General",
        }

    def update_campaign_reference_folder(self, campaign_id: str, reference_id: str, folder: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE campaign_references
                    SET folder = %s
                    WHERE campaign_id = %s AND reference_id = %s;
                    """,
                    (folder, campaign_id, reference_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def delete_campaign_reference(self, campaign_id: str, reference_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM campaign_references
                    WHERE campaign_id = %s AND reference_id = %s
                    RETURNING stored_path;
                    """,
                    (campaign_id, reference_id),
                )
                row = cur.fetchone()
            conn.commit()

        if row is None:
            return None

        return row[0]

    def save_chatbot_audit_log(
        self,
        audit_id: str,
        timestamp: datetime,
        actor_id: str,
        actor_role: str,
        locale: str,
        message: str,
        intent: str,
        ok: bool,
        detail: str | None,
        request_pending_action_type: str | None,
        request_pending_campaign_id: str | None,
        request_pending_reference_id: str | None,
        request_pending_review_id: str | None,
        result_pending_action_type: str | None,
        result_pending_campaign_id: str | None,
        result_pending_reference_id: str | None,
        result_pending_review_id: str | None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chatbot_audit_logs (
                        audit_id, timestamp, actor_id, actor_role, locale, message, intent, ok, detail,
                        request_pending_action_type, request_pending_campaign_id, request_pending_reference_id, request_pending_review_id,
                        result_pending_action_type, result_pending_campaign_id, result_pending_reference_id, result_pending_review_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (audit_id) DO NOTHING;
                    """,
                    (
                        audit_id,
                        timestamp,
                        actor_id,
                        actor_role,
                        locale,
                        message,
                        intent,
                        ok,
                        detail,
                        request_pending_action_type,
                        request_pending_campaign_id,
                        request_pending_reference_id,
                        request_pending_review_id,
                        result_pending_action_type,
                        result_pending_campaign_id,
                        result_pending_reference_id,
                        result_pending_review_id,
                    ),
                )
            conn.commit()

    def list_chatbot_audit_logs(
        self,
        limit: int,
        actor_id: str | None,
        actor_role: str | None,
        intent: str | None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses: list[str] = []
                values: list[Any] = []

                if actor_id:
                    clauses.append("actor_id = %s")
                    values.append(actor_id)
                if actor_role:
                    clauses.append("actor_role = %s")
                    values.append(actor_role)
                if intent:
                    clauses.append("intent = %s")
                    values.append(intent)

                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                values.append(limit)

                cur.execute(
                    f"""
                    SELECT
                        audit_id, timestamp, actor_id, actor_role, locale, message, intent, ok, detail,
                        request_pending_action_type, request_pending_campaign_id, request_pending_reference_id, request_pending_review_id,
                        result_pending_action_type, result_pending_campaign_id, result_pending_reference_id, result_pending_review_id
                    FROM chatbot_audit_logs
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT %s;
                    """,
                    tuple(values),
                )
                rows = cur.fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "audit_id": row[0],
                    "timestamp": row[1],
                    "actor_id": row[2],
                    "actor_role": row[3],
                    "locale": row[4],
                    "message": row[5],
                    "intent": row[6],
                    "ok": bool(row[7]),
                    "detail": row[8],
                    "request_pending_action_type": row[9],
                    "request_pending_campaign_id": row[10],
                    "request_pending_reference_id": row[11],
                    "request_pending_review_id": row[12],
                    "result_pending_action_type": row[13],
                    "result_pending_campaign_id": row[14],
                    "result_pending_reference_id": row[15],
                    "result_pending_review_id": row[16],
                }
            )
        return items

    def create_campaign_trace(
        self,
        trace_id: str,
        campaign_id: str,
        created_by: str,
        source: str,
        created_at: datetime,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO campaign_traces (trace_id, campaign_id, created_by, source, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (campaign_id) DO NOTHING;
                    """,
                    (trace_id, campaign_id, created_by, source, created_at),
                )
            conn.commit()

    def get_campaign_trace_by_campaign_id(self, campaign_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT trace_id, campaign_id, created_by, source, created_at, updated_at
                    FROM campaign_traces
                    WHERE campaign_id = %s
                    LIMIT 1;
                    """,
                    (campaign_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None

        return {
            "trace_id": row[0],
            "campaign_id": row[1],
            "created_by": row[2],
            "source": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def append_campaign_trace_event(
        self,
        event_id: str,
        trace_id: str,
        campaign_id: str,
        event_type: str,
        actor_id: str,
        actor_role: str,
        summary: str,
        payload_json: str,
        created_at: datetime,
        company_id: str,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO campaign_trace_events
                        (event_id, trace_id, campaign_id, event_type, actor_id, actor_role, summary, payload_json, created_at, company_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING;
                    """,
                    (
                        event_id,
                        trace_id,
                        campaign_id,
                        event_type,
                        actor_id,
                        actor_role,
                        summary,
                        payload_json,
                        created_at,
                        company_id,
                    ),
                )
                cur.execute(
                    """
                    UPDATE campaign_traces
                    SET updated_at = NOW()
                    WHERE trace_id = %s;
                    """,
                    (trace_id,),
                )
            conn.commit()

    def append_campaign_chat_message(
        self,
        message_id: str,
        trace_id: str,
        campaign_id: str,
        role: str,
        content_masked: str,
        raw_ref: str | None,
        created_at: datetime,
        company_id: str,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO campaign_chat_transcripts
                        (message_id, trace_id, campaign_id, role, content_masked, raw_ref, created_at, company_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (message_id) DO NOTHING;
                    """,
                    (message_id, trace_id, campaign_id, role, content_masked, raw_ref, created_at, company_id),
                )
                cur.execute(
                    """
                    UPDATE campaign_traces
                    SET updated_at = NOW()
                    WHERE trace_id = %s;
                    """,
                    (trace_id,),
                )
            conn.commit()

    def list_campaign_trace_events(
        self,
        campaign_id: str,
        limit: int,
        cursor_before: tuple[datetime, str] | None,
        event_type: str | None,
        actor_id: str | None,
        keyword: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses = ["campaign_id = %s"]
                values: list[Any] = [campaign_id]

                if cursor_before is not None:
                    clauses.append("(created_at < %s OR (created_at = %s AND event_id < %s))")
                    values.extend([cursor_before[0], cursor_before[0], cursor_before[1]])
                if event_type:
                    clauses.append("event_type = %s")
                    values.append(event_type)
                if actor_id:
                    clauses.append("actor_id = %s")
                    values.append(actor_id)
                if keyword:
                    clauses.append("summary ILIKE %s")
                    values.append(f"%{keyword}%")
                if from_ts is not None:
                    clauses.append("created_at >= %s")
                    values.append(from_ts)
                if to_ts is not None:
                    clauses.append("created_at <= %s")
                    values.append(to_ts)

                where = " AND ".join(clauses)
                values.append(limit)

                cur.execute(
                    f"""
                    SELECT event_id, trace_id, campaign_id, event_type, actor_id, actor_role, summary, payload_json, created_at
                    FROM campaign_trace_events
                    WHERE {where}
                    ORDER BY created_at DESC, event_id DESC
                    LIMIT %s;
                    """,
                    tuple(values),
                )
                rows = cur.fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "event_id": row[0],
                    "trace_id": row[1],
                    "campaign_id": row[2],
                    "event_type": row[3],
                    "actor_id": row[4],
                    "actor_role": row[5],
                    "summary": row[6],
                    "payload_json": row[7],
                    "created_at": row[8],
                }
            )
        return items

    def list_campaign_trace_chat(
        self,
        campaign_id: str,
        limit: int,
        cursor_before: tuple[datetime, str] | None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses = ["campaign_id = %s"]
                values: list[Any] = [campaign_id]
                if cursor_before is not None:
                    clauses.append("(created_at < %s OR (created_at = %s AND message_id < %s))")
                    values.extend([cursor_before[0], cursor_before[0], cursor_before[1]])
                where = " AND ".join(clauses)
                values.append(limit)

                cur.execute(
                    f"""
                    SELECT message_id, trace_id, campaign_id, role, content_masked, raw_ref, created_at
                    FROM campaign_chat_transcripts
                    WHERE {where}
                    ORDER BY created_at DESC, message_id DESC
                    LIMIT %s;
                    """,
                    tuple(values),
                )
                rows = cur.fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "message_id": row[0],
                    "trace_id": row[1],
                    "campaign_id": row[2],
                    "role": row[3],
                    "content_masked": row[4],
                    "raw_ref": row[5],
                    "created_at": row[6],
                }
            )
        return items

    def count_campaign_trace_events(self, campaign_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM campaign_trace_events
                    WHERE campaign_id = %s;
                    """,
                    (campaign_id,),
                )
                row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_campaign_trace_events_filtered(
        self,
        campaign_id: str,
        event_type: str | None,
        actor_id: str | None,
        keyword: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses = ["campaign_id = %s"]
                values: list[Any] = [campaign_id]

                if event_type:
                    clauses.append("event_type = %s")
                    values.append(event_type)
                if actor_id:
                    clauses.append("actor_id = %s")
                    values.append(actor_id)
                if keyword:
                    clauses.append("summary ILIKE %s")
                    values.append(f"%{keyword}%")
                if from_ts is not None:
                    clauses.append("created_at >= %s")
                    values.append(from_ts)
                if to_ts is not None:
                    clauses.append("created_at <= %s")
                    values.append(to_ts)

                where = " AND ".join(clauses)
                cur.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM campaign_trace_events
                    WHERE {where};
                    """,
                    tuple(values),
                )
                row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])

    def count_campaign_trace_chat(self, campaign_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM campaign_chat_transcripts
                    WHERE campaign_id = %s;
                    """,
                    (campaign_id,),
                )
                row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])

    def create_work_order(
        self,
        work_order_id: str,
        campaign_id: str,
        task_id: str | None,
        title: str,
        description: str,
        assignee: str | None,
        status: str,
        priority: int,
        created_by: str,
        due_at: datetime | None,
        created_at: datetime,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO work_orders
                        (work_order_id, campaign_id, task_id, title, description, assignee, status, priority, created_by, due_at, escalated_at, escalation_reason, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (work_order_id) DO NOTHING;
                    """,
                    (
                        work_order_id,
                        campaign_id,
                        task_id,
                        title,
                        description,
                        assignee,
                        status,
                        priority,
                        created_by,
                        due_at,
                        None,
                        None,
                        created_at,
                        created_at,
                    ),
                )
            conn.commit()

    def get_work_order(self, work_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT work_order_id, campaign_id, task_id, title, description, assignee, status, priority, created_by, due_at, escalated_at, escalation_reason, created_at, updated_at
                    FROM work_orders
                    WHERE work_order_id = %s
                    LIMIT 1;
                    """,
                    (work_order_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None
        return {
            "work_order_id": row[0],
            "campaign_id": row[1],
            "task_id": row[2],
            "title": row[3],
            "description": row[4],
            "assignee": row[5],
            "status": row[6],
            "priority": int(row[7]),
            "created_by": row[8],
            "due_at": row[9],
            "escalated_at": row[10],
            "escalation_reason": row[11],
            "created_at": row[12],
            "updated_at": row[13],
        }

    def list_campaign_work_orders(
        self,
        campaign_id: str,
        limit: int,
        cursor_before: tuple[datetime, str] | None,
        status: str | None,
        assignee: str | None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses = ["campaign_id = %s"]
                values: list[Any] = [campaign_id]
                if cursor_before is not None:
                    clauses.append("(updated_at < %s OR (updated_at = %s AND work_order_id < %s))")
                    values.extend([cursor_before[0], cursor_before[0], cursor_before[1]])
                if status:
                    clauses.append("status = %s")
                    values.append(status)
                if assignee:
                    clauses.append("assignee = %s")
                    values.append(assignee)
                values.append(limit)
                where = " AND ".join(clauses)
                cur.execute(
                    f"""
                    SELECT work_order_id, campaign_id, task_id, title, description, assignee, status, priority, created_by, due_at, escalated_at, escalation_reason, created_at, updated_at
                    FROM work_orders
                    WHERE {where}
                    ORDER BY updated_at DESC, work_order_id DESC
                    LIMIT %s;
                    """,
                    tuple(values),
                )
                rows = cur.fetchall()

        return [
            {
                "work_order_id": row[0],
                "campaign_id": row[1],
                "task_id": row[2],
                "title": row[3],
                "description": row[4],
                "assignee": row[5],
                "status": row[6],
                "priority": int(row[7]),
                "created_by": row[8],
                "due_at": row[9],
                "escalated_at": row[10],
                "escalation_reason": row[11],
                "created_at": row[12],
                "updated_at": row[13],
            }
            for row in rows
        ]

    def count_campaign_work_orders(self, campaign_id: str, status: str | None, assignee: str | None) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses = ["campaign_id = %s"]
                values: list[Any] = [campaign_id]
                if status:
                    clauses.append("status = %s")
                    values.append(status)
                if assignee:
                    clauses.append("assignee = %s")
                    values.append(assignee)
                where = " AND ".join(clauses)
                cur.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM work_orders
                    WHERE {where};
                    """,
                    tuple(values),
                )
                row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])

    def update_work_order(
        self,
        work_order_id: str,
        title: str | None,
        description: str | None,
        assignee: str | None,
        status: str | None,
        priority: int | None,
        due_at: datetime | None,
        clear_escalation: bool,
        updated_at: datetime,
    ) -> bool:
        set_clauses: list[str] = []
        values: list[Any] = []
        if title is not None:
            set_clauses.append("title = %s")
            values.append(title)
        if description is not None:
            set_clauses.append("description = %s")
            values.append(description)
        if assignee is not None:
            set_clauses.append("assignee = %s")
            values.append(assignee)
        if status is not None:
            set_clauses.append("status = %s")
            values.append(status)
        if priority is not None:
            set_clauses.append("priority = %s")
            values.append(priority)
        if due_at is not None or clear_escalation:
            set_clauses.append("due_at = %s")
            values.append(due_at)
        if clear_escalation:
            set_clauses.append("escalated_at = NULL")
            set_clauses.append("escalation_reason = NULL")
        if not set_clauses:
            return False

        set_clauses.append("updated_at = %s")
        values.append(updated_at)
        values.append(work_order_id)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE work_orders
                    SET {', '.join(set_clauses)}
                    WHERE work_order_id = %s;
                    """,
                    tuple(values),
                )
                affected = cur.rowcount
            conn.commit()
        return affected > 0

    def update_work_order_escalation(
        self,
        work_order_id: str,
        escalated_at: datetime,
        escalation_reason: str,
        updated_at: datetime,
    ) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE work_orders
                    SET escalated_at = %s, escalation_reason = %s, updated_at = %s
                    WHERE work_order_id = %s
                      AND escalated_at IS NULL;
                    """,
                    (escalated_at, escalation_reason, updated_at, work_order_id),
                )
                affected = cur.rowcount
            conn.commit()
        return affected > 0

    def append_work_order_message(
        self,
        message_id: str,
        work_order_id: str,
        campaign_id: str,
        role: str,
        content_masked: str,
        actor_id: str,
        created_at: datetime,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO work_order_messages
                        (message_id, work_order_id, campaign_id, role, content_masked, actor_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (message_id) DO NOTHING;
                    """,
                    (message_id, work_order_id, campaign_id, role, content_masked, actor_id, created_at),
                )
                cur.execute(
                    """
                    UPDATE work_orders
                    SET updated_at = %s
                    WHERE work_order_id = %s;
                    """,
                    (created_at, work_order_id),
                )
            conn.commit()

    def list_work_order_messages(
        self,
        work_order_id: str,
        limit: int,
        cursor_before: tuple[datetime, str] | None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                clauses = ["work_order_id = %s"]
                values: list[Any] = [work_order_id]
                if cursor_before is not None:
                    clauses.append("(created_at < %s OR (created_at = %s AND message_id < %s))")
                    values.extend([cursor_before[0], cursor_before[0], cursor_before[1]])
                where = " AND ".join(clauses)
                values.append(limit)
                cur.execute(
                    f"""
                    SELECT message_id, work_order_id, campaign_id, role, content_masked, actor_id, created_at
                    FROM work_order_messages
                    WHERE {where}
                    ORDER BY created_at DESC, message_id DESC
                    LIMIT %s;
                    """,
                    tuple(values),
                )
                rows = cur.fetchall()

        return [
            {
                "message_id": row[0],
                "work_order_id": row[1],
                "campaign_id": row[2],
                "role": row[3],
                "content_masked": row[4],
                "actor_id": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def count_work_order_messages(self, work_order_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM work_order_messages
                    WHERE work_order_id = %s;
                    """,
                    (work_order_id,),
                )
                row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])

    def summarize_trace_health(self) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM campaign_traces),
                        (SELECT COUNT(*) FROM campaign_trace_events),
                        (SELECT COUNT(*) FROM campaign_chat_transcripts),
                        (SELECT COUNT(*) FROM work_orders),
                        (SELECT COUNT(*) FROM work_order_messages),
                        (SELECT COUNT(*) FROM work_orders WHERE due_at IS NOT NULL AND due_at < NOW() AND status NOT IN ('done', 'cancelled')),
                        (SELECT COUNT(*) FROM work_orders WHERE escalated_at IS NOT NULL);
                    """
                )
                totals_row = cur.fetchone()

                cur.execute(
                    """
                    SELECT event_type, COUNT(*) AS total
                    FROM campaign_trace_events
                    GROUP BY event_type
                    ORDER BY total DESC, event_type ASC
                    LIMIT 10;
                    """
                )
                type_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT created_at
                    FROM campaign_trace_events
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """
                )
                latest_event_row = cur.fetchone()

                cur.execute(
                    """
                    SELECT created_at
                    FROM campaign_chat_transcripts
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """
                )
                latest_chat_row = cur.fetchone()

        trace_total = int(totals_row[0]) if totals_row is not None else 0
        event_total = int(totals_row[1]) if totals_row is not None else 0
        chat_total = int(totals_row[2]) if totals_row is not None else 0
        work_order_total = int(totals_row[3]) if totals_row is not None else 0
        work_order_message_total = int(totals_row[4]) if totals_row is not None else 0
        work_order_overdue_total = int(totals_row[5]) if totals_row is not None else 0
        work_order_escalated_total = int(totals_row[6]) if totals_row is not None else 0

        return {
            "trace_total": trace_total,
            "event_total": event_total,
            "chat_total": chat_total,
            "work_order_total": work_order_total,
            "work_order_message_total": work_order_message_total,
            "work_order_overdue_total": work_order_overdue_total,
            "work_order_escalated_total": work_order_escalated_total,
            "top_event_types": [{"event_type": str(row[0]), "total": int(row[1])} for row in type_rows],
            "latest_event_at": latest_event_row[0] if latest_event_row is not None else None,
            "latest_chat_at": latest_chat_row[0] if latest_chat_row is not None else None,
        }

    def list_overdue_unescalated_work_orders(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT work_order_id, campaign_id, task_id, title, description, assignee, status, priority, created_by,
                           due_at, escalated_at, escalation_reason, created_at, updated_at
                    FROM work_orders
                    WHERE due_at IS NOT NULL
                      AND due_at < NOW()
                      AND escalated_at IS NULL
                      AND status NOT IN ('done', 'cancelled')
                    ORDER BY due_at ASC
                    LIMIT %s;
                    """,
                    (max(1, min(limit, 5000)),),
                )
                rows = cur.fetchall()
        return [
            {
                "work_order_id": row[0],
                "campaign_id": row[1],
                "task_id": row[2],
                "title": row[3],
                "description": row[4],
                "assignee": row[5],
                "status": row[6],
                "priority": int(row[7]),
                "created_by": row[8],
                "due_at": row[9],
                "escalated_at": row[10],
                "escalation_reason": row[11],
                "created_at": row[12],
                "updated_at": row[13],
            }
            for row in rows
        ]

    def count_overdue_unescalated_work_orders(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM work_orders
                    WHERE due_at IS NOT NULL
                      AND due_at < NOW()
                      AND escalated_at IS NULL
                      AND status NOT IN ('done', 'cancelled');
                    """
                )
                row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])

    def cleanup_campaign_trace_before(self, cutoff: datetime) -> dict[str, int]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM campaign_trace_events
                    WHERE created_at < %s;
                    """,
                    (cutoff,),
                )
                deleted_events = cur.rowcount

                cur.execute(
                    """
                    DELETE FROM campaign_chat_transcripts
                    WHERE created_at < %s;
                    """,
                    (cutoff,),
                )
                deleted_chat = cur.rowcount

                cur.execute(
                    """
                    DELETE FROM campaign_traces ct
                    WHERE NOT EXISTS (
                        SELECT 1 FROM campaign_trace_events e WHERE e.trace_id = ct.trace_id
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM campaign_chat_transcripts c WHERE c.trace_id = ct.trace_id
                    )
                    AND ct.updated_at < %s;
                    """,
                    (cutoff,),
                )
                deleted_traces = cur.rowcount
            conn.commit()

        return {
            "deleted_events": int(deleted_events),
            "deleted_chat": int(deleted_chat),
            "deleted_traces": int(deleted_traces),
        }

    # ─── LLM Usage ─────────────────────────────────────────────────────────────────

    def initialize_llm_tables(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Enable uuid-ossp extension (required for uuid_generate_v4)
                cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_usage (
                        usage_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        company_id      UUID NOT NULL,
                        model           VARCHAR(100) NOT NULL,
                        provider        VARCHAR(50) NOT NULL,
                        prompt_tokens   BIGINT NOT NULL DEFAULT 0,
                        completion_tokens BIGINT NOT NULL DEFAULT 0,
                        request_count   INTEGER NOT NULL DEFAULT 1,
                        raw_response_id VARCHAR(255),
                        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_model_pricing (
                        pricing_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        model                   VARCHAR(100) UNIQUE NOT NULL,
                        provider                VARCHAR(50) NOT NULL,
                        prompt_price_per_m      DECIMAL(10,4) NOT NULL DEFAULT 0,
                        completion_price_per_m  DECIMAL(10,4) NOT NULL DEFAULT 0,
                        is_active               BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    INSERT INTO llm_model_pricing (model, provider, prompt_price_per_m, completion_price_per_m)
                    VALUES ('deepseek-v3', 'deepseek', 0.27, 1.10)
                    ON CONFLICT (model) DO NOTHING;
                    """
                )
                cur.execute(
                    """
                    INSERT INTO llm_model_pricing (model, provider, prompt_price_per_m, completion_price_per_m)
                    VALUES ('deepseek-v4-flash', 'deepseek', 0, 0)
                    ON CONFLICT (model) DO NOTHING;
                    """
                )
                cur.execute(
                    """
                    INSERT INTO llm_model_pricing (model, provider, prompt_price_per_m, completion_price_per_m)
                    VALUES ('minimax-video-01', 'minimax', 0, 0)
                    ON CONFLICT (model) DO NOTHING;
                    """
                )
                cur.execute(
                    """
                    INSERT INTO llm_model_pricing (model, provider, prompt_price_per_m, completion_price_per_m)
                    VALUES ('MiniMax-Hailuo-2.3', 'minimax', 0, 0)
                    ON CONFLICT (model) DO NOTHING;
                    """
                )
                conn.commit()

    def flush_llm_usage_batch(self, rows: list[dict[str, Any]]) -> None:
        """Bulk insert from Redis buffer."""
        if not rows:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                for item in rows:
                    cur.execute(
                        """
                        INSERT INTO llm_usage
                            (company_id, model, provider, prompt_tokens, completion_tokens, request_count, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            item["company_id"],
                            item["model"],
                            item["provider"],
                            int(item["prompt_tokens"]),
                            int(item["completion_tokens"]),
                            int(item.get("request_count", 1)),
                            item.get("created_at", datetime.utcnow()),
                        ),
                    )
            conn.commit()

    def list_llm_usage(
        self,
        company_id: str | None,
        model: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        clauses = []
        values: list[Any] = []
        if company_id:
            clauses.append("company_id = %s")
            values.append(company_id)
        if model:
            clauses.append("model = %s")
            values.append(model)
        if from_ts:
            clauses.append("created_at >= %s")
            values.append(from_ts)
        if to_ts:
            clauses.append("created_at <= %s")
            values.append(to_ts)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        values.extend([limit, offset])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT usage_id, company_id, model, provider,
                           prompt_tokens, completion_tokens, request_count, created_at
                    FROM llm_usage
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s;
                    """,
                    tuple(values),
                )
                return [
                    {
                        "usage_id": str(row[0]),
                        "company_id": str(row[1]),
                        "model": row[2],
                        "provider": row[3],
                        "prompt_tokens": int(row[4]),
                        "completion_tokens": int(row[5]),
                        "request_count": int(row[6]),
                        "created_at": row[7],
                    }
                    for row in cur.fetchall()
                ]

    def count_llm_usage(
        self,
        company_id: str | None,
        model: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> int:
        clauses = []
        values: list[Any] = []
        if company_id:
            clauses.append("company_id = %s")
            values.append(company_id)
        if model:
            clauses.append("model = %s")
            values.append(model)
        if from_ts:
            clauses.append("created_at >= %s")
            values.append(from_ts)
        if to_ts:
            clauses.append("created_at <= %s")
            values.append(to_ts)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM llm_usage {where};",
                    tuple(values),
                )
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def summarize_llm_usage(
        self,
        company_id: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> dict[str, Any]:
        clauses = []
        values: list[Any] = []
        if company_id:
            clauses.append("company_id = %s")
            values.append(company_id)
        if from_ts:
            clauses.append("created_at >= %s")
            values.append(from_ts)
        if to_ts:
            clauses.append("created_at <= %s")
            values.append(to_ts)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(prompt_tokens), 0),
                        COALESCE(SUM(completion_tokens), 0),
                        COALESCE(SUM(request_count), 0)
                    FROM llm_usage
                    {where};
                    """,
                    tuple(values),
                )
                total_row = cur.fetchone()
                cur.execute(
                    f"""
                    SELECT model, provider,
                           COALESCE(SUM(prompt_tokens), 0),
                           COALESCE(SUM(completion_tokens), 0),
                           COALESCE(SUM(request_count), 0)
                    FROM llm_usage
                    {where}
                    GROUP BY model, provider
                    ORDER BY model;
                    """,
                    tuple(values),
                )
                by_model = [
                    {
                        "model": str(r[0]),
                        "provider": str(r[1]),
                        "prompt_tokens": int(r[2]),
                        "completion_tokens": int(r[3]),
                        "request_count": int(r[4]),
                    }
                    for r in cur.fetchall()
                ]
        return {
            "total_prompt_tokens": int(total_row[0]) if total_row else 0,
            "total_completion_tokens": int(total_row[1]) if total_row else 0,
            "total_request_count": int(total_row[2]) if total_row else 0,
            "by_model": by_model,
        }

    def list_llm_model_pricing(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if include_inactive:
                    cur.execute(
                        """
                        SELECT pricing_id, model, provider, prompt_price_per_m,
                               completion_price_per_m, is_active, created_at, updated_at
                        FROM llm_model_pricing
                        ORDER BY model;
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT pricing_id, model, provider, prompt_price_per_m,
                               completion_price_per_m, is_active, created_at, updated_at
                        FROM llm_model_pricing
                        WHERE is_active = TRUE
                        ORDER BY model;
                        """
                    )
                return [
                    {
                        "pricing_id": str(row[0]),
                        "model": row[1],
                        "provider": row[2],
                        "prompt_price_per_m": float(row[3]),
                        "completion_price_per_m": float(row[4]),
                        "is_active": bool(row[5]),
                        "created_at": row[6],
                        "updated_at": row[7],
                    }
                    for row in cur.fetchall()
                ]

    def upsert_llm_model_pricing(
        self,
        model: str,
        provider: str,
        prompt_price_per_m: float,
        completion_price_per_m: float,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_model_pricing
                        (model, provider, prompt_price_per_m, completion_price_per_m, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON CONFLICT (model) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        prompt_price_per_m = EXCLUDED.prompt_price_per_m,
                        completion_price_per_m = EXCLUDED.completion_price_per_m,
                        is_active = TRUE,
                        updated_at = now();
                    """,
                    (model, provider, prompt_price_per_m, completion_price_per_m),
                )
            conn.commit()

    def soft_delete_llm_model_pricing(self, model: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE llm_model_pricing
                    SET is_active = FALSE, updated_at = now()
                    WHERE model = %s;
                    """,
                    (model,),
                )
            conn.commit()

    def list_knowledge_items(self, company_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item_id, company_id, title, source, description, content_url, metadata_json, created_at
                    FROM knowledge_items
                    WHERE company_id = %s AND deleted_at IS NULL
                    ORDER BY created_at DESC;
                    """,
                    (company_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "item_id": row[0],
                "company_id": row[1],
                "title": row[2],
                "source": row[3],
                "description": row[4],
                "content_url": row[5],
                "metadata": dict(row[6] or {}),
                "created_at": row[7],
            }
            for row in rows
        ]

    def create_knowledge_item(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_items
                        (item_id, company_id, title, source, description, content_url, metadata_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (item_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source = EXCLUDED.source,
                        description = EXCLUDED.description,
                        content_url = EXCLUDED.content_url,
                        metadata_json = EXCLUDED.metadata_json,
                        deleted_at = NULL;
                    """,
                    (
                        item["item_id"],
                        item["company_id"],
                        item["title"],
                        item["source"],
                        item.get("description", ""),
                        item.get("content_url"),
                        json.dumps(item.get("metadata", {})),
                        item["created_at"],
                    ),
                )
            conn.commit()
        return item

    def update_knowledge_item(self, company_id: str, item_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current_items = self.list_knowledge_items(company_id)
        current = next((item for item in current_items if item.get("item_id") == item_id), None)
        if current is None:
            return None
        metadata = dict(current.get("metadata") or {})
        if isinstance(updates.get("metadata"), dict):
            metadata.update(updates["metadata"])
        if "category" in updates and updates["category"] is not None:
            metadata["category"] = str(updates["category"]).strip()
        title = str(updates.get("title") or current.get("title") or "").strip()
        description = str(updates.get("description") if updates.get("description") is not None else current.get("description") or "").strip()
        content_url = updates.get("content_url") if updates.get("content_url") is not None else current.get("content_url")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE knowledge_items
                    SET title = %s,
                        description = %s,
                        content_url = %s,
                        metadata_json = %s::jsonb
                    WHERE company_id = %s AND item_id = %s AND deleted_at IS NULL
                    RETURNING item_id, company_id, title, source, description, content_url, metadata_json, created_at;
                    """,
                    (title, description, content_url, json.dumps(metadata), company_id, item_id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return {
            "item_id": row[0],
            "company_id": row[1],
            "title": row[2],
            "source": row[3],
            "description": row[4],
            "content_url": row[5],
            "metadata": dict(row[6] or {}),
            "created_at": row[7],
        }

    def soft_delete_knowledge_item(self, company_id: str, item_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE knowledge_items
                    SET deleted_at = %s
                    WHERE company_id = %s AND item_id = %s AND deleted_at IS NULL;
                    """,
                    (datetime.utcnow(), company_id, item_id),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def upsert_workflow_template(self, template: dict[str, Any], versions: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_templates
                        (template_id, name, description, active_version, status, versions_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                    ON CONFLICT (template_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        active_version = EXCLUDED.active_version,
                        status = EXCLUDED.status,
                        versions_json = EXCLUDED.versions_json,
                        updated_at = NOW();
                    """,
                    (
                        template["template_id"],
                        template["name"],
                        template.get("description", ""),
                        template.get("active_version", 1),
                        template.get("status", "active"),
                        json.dumps(versions),
                        template["created_at"],
                    ),
                )
            conn.commit()

    def list_workflow_templates(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT template_id, name, description, active_version, status, versions_json, created_at
                    FROM workflow_templates
                    ORDER BY created_at DESC;
                    """
                )
                rows = cur.fetchall()
        return [
            {
                "template": {
                    "template_id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "active_version": row[3],
                    "status": row[4],
                    "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
                },
                "versions": list(row[5] or []),
            }
            for row in rows
        ]

    def set_workflow_template_status(self, template_id: str, status: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workflow_templates SET status = %s, updated_at = NOW() WHERE template_id = %s",
                    (status, template_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    # ── Webhook subscriptions ────────────────────────────────────────────────

    def upsert_webhook_subscription(
        self,
        sub_id: str,
        company_id: str,
        url: str,
        secret: str,
        events: list[str],
        active: bool = True,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO webhook_subscriptions (sub_id, company_id, url, secret, events, active)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (sub_id) DO UPDATE SET
                        company_id = EXCLUDED.company_id,
                        url = EXCLUDED.url,
                        secret = EXCLUDED.secret,
                        events = EXCLUDED.events,
                        active = EXCLUDED.active,
                        updated_at = NOW();
                    """,
                    (sub_id, company_id, url, secret, json.dumps(events), active),
                )
            conn.commit()

    def list_webhook_subscriptions(self, company_id: str | None = None, active: bool | None = None) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if company_id is not None:
            where.append("company_id = %s")
            params.append(company_id)
        if active is not None:
            where.append("active = %s")
            params.append(active)
        clause = "WHERE " + " AND ".join(where) if where else ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT sub_id, company_id, url, secret, events, active, created_at, updated_at
                    FROM webhook_subscriptions
                    {clause}
                    ORDER BY created_at DESC;
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return [
            {
                "sub_id": row[0],
                "company_id": row[1],
                "url": row[2],
                "secret": row[3],
                "events": row[4] or [],
                "active": bool(row[5]),
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def delete_webhook_subscription(self, sub_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM webhook_subscriptions WHERE sub_id = %s", (sub_id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def log_webhook_delivery(
        self,
        log_id: str,
        sub_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        response_code: int | None,
        response_body: str | None,
        attempt: int,
        status: str,
        next_retry_at: datetime | None = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO webhook_delivery_log
                        (log_id, sub_id, event_type, payload_json, response_code, response_body, attempt, status, next_retry_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s);
                    """,
                    (log_id, sub_id, event_type, json.dumps(payload_json), response_code, response_body, attempt, status, next_retry_at),
                )
            conn.commit()

    def list_webhook_delivery_logs(self, sub_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT log_id, sub_id, event_type, payload_json, response_code, response_body, attempt, delivered_at, next_retry_at, status
                    FROM webhook_delivery_log
                    WHERE sub_id = %s
                    ORDER BY delivered_at DESC
                    LIMIT %s;
                    """,
                    (sub_id, limit),
                )
                rows = cur.fetchall()
        return [
            {
                "log_id": row[0],
                "sub_id": row[1],
                "event_type": row[2],
                "payload": row[3] or {},
                "response_code": row[4],
                "response_body": row[5],
                "attempt": row[6],
                "delivered_at": row[7],
                "next_retry_at": row[8],
                "status": row[9],
            }
            for row in rows
        ]


def now_utc() -> datetime:
    return datetime.utcnow()
