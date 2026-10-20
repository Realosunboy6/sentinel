from django.db import migrations, models
from apps.core.migration_helpers import convert_key


def forward(apps, editor):
    convert_key(apps, editor, 'analysis', 'AnalysisResult', ('input_hash', 'data_asof'))


def backward(apps, editor):
    convert_key(apps, editor, 'analysis', 'AnalysisResult', ('input_hash', 'data_asof'), reverse=True)


def postgres_defaults(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    for table in ('securities', 'corporate_actions', 'analyses'):
        editor.execute(f'ALTER TABLE {table} ALTER COLUMN id SET DEFAULT gen_random_uuid()')
    for table, column, value in (('securities', 'exchange', "''"), ('securities', 'asset_type', "'stock'"), ('securities', 'currency', "'USD'"), ('analyses', 'created_at', 'now()'), ('analysis_results', 'computed_at', 'now()')):
        editor.execute(f'ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {value}')
    with editor.connection.cursor() as cursor:
        for table in ('price_history', 'corporate_actions'):
            constraints = editor.connection.introspection.get_constraints(cursor, table)
            for name, detail in constraints.items():
                if detail.get('foreign_key') == ('securities', 'id'):
                    editor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {editor.quote_name(name)}')
            editor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_security_fk FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED')


class Migration(migrations.Migration):
    dependencies = [('analysis', '0001_initial'), ('marketdata', '0002_locked_schema')]
    operations = [
        migrations.AlterModelTable('analysis', 'analyses'),
        migrations.AlterModelTable('analysisresult', 'analysis_results'),
        migrations.AlterModelTable('preset', 'presets'),
        migrations.AlterUniqueTogether('analysisresult', set()),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(forward, backward)],
            state_operations=[migrations.RemoveField('analysisresult', 'id'),
                              migrations.AddField('analysisresult', 'pk', models.CompositePrimaryKey('input_hash', 'data_asof', blank=True, editable=False, primary_key=True, serialize=False))],
        ),
        migrations.RunPython(postgres_defaults, migrations.RunPython.noop),
    ]
