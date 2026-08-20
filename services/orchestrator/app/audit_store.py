import importlib
from dataclasses import dataclass


psycopg = importlib.import_module("psycopg")


@dataclass
class AuditQueryResult:
    items: list[dict]
    total: int


class OperationAuditStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _connect(self):
        return psycopg.connect(self._dsn)

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS operation_audit_logs (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        operator TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        target TEXT NOT NULL,
                        result TEXT NOT NULL,
                        detail TEXT NOT NULL
                    );
                    """
                )
            conn.commit()

    def append(self, timestamp: str, operator: str, operation: str, target: str, result: str, detail: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO operation_audit_logs
                        (timestamp, operator, operation, target, result, detail)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (timestamp, operator, operation, target, result, detail),
                )
            conn.commit()

    def query(
        self,
        page: int,
        page_size: int,
        operator: str | None,
        operation: str | None,
        result: str | None,
    ) -> AuditQueryResult:
        conditions: list[str] = []
        params: list[object] = []

        if operator:
            conditions.append("operator = %s")
            params.append(operator)
        if operation:
            conditions.append("operation = %s")
            params.append(operation)
        if result:
            conditions.append("result = %s")
            params.append(result)

        where_sql = ""
        if conditions:
            where_sql = " WHERE " + " AND ".join(conditions)

        offset = (page - 1) * page_size
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM operation_audit_logs{where_sql};", params)
                total = int(cur.fetchone()[0])

                cur.execute(
                    f"""
                    SELECT timestamp, operator, operation, target, result, detail
                    FROM operation_audit_logs
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT %s OFFSET %s;
                    """,
                    [*params, page_size, offset],
                )
                rows = cur.fetchall()

        items = [
            {
                "timestamp": row[0].isoformat(),
                "operator": row[1],
                "operation": row[2],
                "target": row[3],
                "result": row[4],
                "detail": row[5],
            }
            for row in rows
        ]
        return AuditQueryResult(items=items, total=total)
