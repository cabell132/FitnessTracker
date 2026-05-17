# ruff: noqa: INP001
"""Copy the local SQLite fitness tracker database into PostgreSQL."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import Column, Table

from fitness_tracker.database.config import DEFAULT_DATABASE_URL, get_database_url
from fitness_tracker.database.models import BaseModel

CHUNK_SIZE = 1000
SOURCE_URL_ERROR = "--source-url must be a SQLite URL"
TARGET_URL_ERROR = "--target-url must be a PostgreSQL URL"
MISSING_TARGET_ERROR = "Set DATABASE_URL or pass --target-url"


def main() -> int:
    """Run the SQLite-to-Postgres migration."""
    load_dotenv()
    args = _parse_args()
    source_engine = create_engine(args.source_url)
    target_engine = create_engine(args.target_url)

    if source_engine.url.get_backend_name() != "sqlite":
        raise SystemExit(SOURCE_URL_ERROR)
    if not target_engine.url.get_backend_name().startswith("postgresql"):
        raise SystemExit(TARGET_URL_ERROR)

    if args.replace:
        BaseModel.metadata.drop_all(target_engine)
    BaseModel.metadata.create_all(target_engine)

    with source_engine.connect() as source, target_engine.begin() as target:
        migrator = TableMigrator(source=source, target=target)
        for table in BaseModel.metadata.sorted_tables:
            count = migrator.copy_table(table)
            _emit(f"{table.name}: copied {count} rows")
        _reset_postgres_sequences(target_engine, target, BaseModel.metadata.sorted_tables)

    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url",
        default=DEFAULT_DATABASE_URL,
        help="SQLite SQLAlchemy URL. Defaults to sqlite:///fitness_tracker.db.",
    )
    parser.add_argument(
        "--target-url",
        default=get_database_url(""),
        help="PostgreSQL SQLAlchemy URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and recreate target tables before copying.",
    )
    args = parser.parse_args()
    if not args.target_url:
        raise SystemExit(MISSING_TARGET_ERROR)
    return args


@dataclass
class TableMigrator:
    """Copy rows while normalizing SQLite-tolerated orphan references."""

    source: Connection
    target: Connection
    reference_cache: dict[tuple[str, str], set[Any]] = field(default_factory=dict)

    def copy_table(self, table: Table) -> int:
        """Copy one table from SQLite to PostgreSQL."""
        count = 0
        batch: list[dict[str, Any]] = []
        for row in self.source.execute(select(table)).mappings():
            batch.append(self._with_nullable_orphan_fks_removed(table, dict(row)))
            if len(batch) >= CHUNK_SIZE:
                self.target.execute(table.insert(), batch)
                count += len(batch)
                batch.clear()
        if batch:
            self.target.execute(table.insert(), batch)
            count += len(batch)
        return count

    def _with_nullable_orphan_fks_removed(
        self,
        table: Table,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        for foreign_key in table.foreign_keys:
            local_column = foreign_key.parent
            value = row.get(local_column.name)
            if value is None or not local_column.nullable:
                continue
            valid_values = self._reference_values(foreign_key.column)
            if value not in valid_values:
                row[local_column.name] = None
        return row

    def _reference_values(self, column: Column[Any]) -> set[Any]:
        key = (column.table.name, column.name)
        if key not in self.reference_cache:
            self.reference_cache[key] = {
                value
                for value in self.source.execute(select(column)).scalars()
                if value is not None
            }
        return self.reference_cache[key]


def _reset_postgres_sequences(
    engine: Engine,
    connection: Connection,
    tables: Iterable[Table],
) -> None:
    preparer = engine.dialect.identifier_preparer
    for table in tables:
        integer_pk = [
            column for column in table.primary_key.columns if column.type.python_type is int
        ]
        if len(integer_pk) != 1:
            continue
        column = integer_pk[0]
        sequence_name = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": f'"{table.name}"', "column_name": column.name},
        ).scalar()
        if sequence_name is None:
            continue
        table_name = preparer.quote(table.name)
        column_name = preparer.quote(column.name)
        max_id = connection.execute(
            text(f"SELECT MAX({column_name}) FROM {table_name}")  # noqa: S608
        ).scalar()
        connection.execute(
            text("SELECT setval(:sequence_name, :value, :is_called)"),
            {
                "sequence_name": sequence_name,
                "value": max_id or 1,
                "is_called": max_id is not None,
            },
        )


def _emit(message: str) -> None:
    print(message)  # noqa: T201


if __name__ == "__main__":
    raise SystemExit(main())
