"""Compare migrated business tables with the supplied DDL in a temporary schema.

PowerShell: set DATABASE_URL to the isolated verification database, then run
python scripts/verify_postgres_schema.py. No business data is changed.
"""
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

TABLES = ['securities', 'price_history', 'corporate_actions', 'analyses', 'analysis_results', 'presets']


def columns(cursor, schema, table):
    cursor.execute("""SELECT column_name, data_type, udt_name, is_nullable,
        character_maximum_length, numeric_precision, numeric_scale, column_default
        FROM information_schema.columns WHERE table_schema=%s AND table_name=%s
        ORDER BY column_name""", (schema, table))
    return cursor.fetchall()


def primary_key(cursor, schema, table):
    cursor.execute("""SELECT k.column_name FROM information_schema.table_constraints t
        JOIN information_schema.key_column_usage k ON t.constraint_name=k.constraint_name
        AND t.constraint_schema=k.constraint_schema AND t.table_name=k.table_name
        WHERE t.constraint_type='PRIMARY KEY' AND t.table_schema=%s AND t.table_name=%s
        ORDER BY k.ordinal_position""", (schema, table))
    return [row[0] for row in cursor.fetchall()]


def verify():
    ddl = (Path(__file__).resolve().parents[1] / 'docs/design/sentinel-schema.sql').read_text(encoding='utf-8')
    # gen_random_uuid() is built into PostgreSQL 15. Compare the six table
    # definitions without creating/removing a database-wide extension.
    ddl = ddl.replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;', '')
    schema = 'sentinel_reference_' + uuid.uuid4().hex[:12]
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            cursor.execute(sql.SQL('SET LOCAL search_path TO {}, public').format(sql.Identifier(schema)))
            cursor.execute(ddl)
            result = {}
            for table in TABLES:
                expected, actual = columns(cursor, schema, table), columns(cursor, 'public', table)
                expected_pk, actual_pk = primary_key(cursor, schema, table), primary_key(cursor, 'public', table)
                result[table] = {'columns_match': actual == expected, 'primary_key_match': actual_pk == expected_pk}
                if actual != expected:
                    result[table].update(expected_columns=expected, actual_columns=actual)
            cursor.execute("""SELECT c.relname, con.confdeltype FROM pg_constraint con
                JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname IN ('price_history','corporate_actions')
                AND con.contype='f'""")
            result['cascades'] = all(row[1] == 'c' for row in cursor.fetchall())
            cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    print(json.dumps(result, indent=2, default=str))
    assert all(result[table]['columns_match'] and result[table]['primary_key_match'] for table in TABLES), 'Locked DDL differs from migrated business tables'
    assert result['cascades'], 'Missing database-level cascade'


if __name__ == '__main__':
    verify()
