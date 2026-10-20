from django.db import migrations, models
from apps.core.fields import FixedCharField
from apps.core.migration_helpers import convert_key


def forward(apps, editor):
    convert_key(apps, editor, 'marketdata', 'PriceHistory', ('security_id', 'date'))


def backward(apps, editor):
    convert_key(apps, editor, 'marketdata', 'PriceHistory', ('security_id', 'date'), reverse=True)


class Migration(migrations.Migration):
    dependencies = [('marketdata', '0001_initial')]
    operations = [
        migrations.AlterModelTable('security', 'securities'),
        migrations.AlterModelTable('pricehistory', 'price_history'),
        migrations.AlterModelTable('corporateaction', 'corporate_actions'),
        migrations.AlterField('security', 'currency', FixedCharField(default='USD', max_length=3)),
        migrations.AlterField('corporateaction', 'action_type', models.TextField(choices=[('SPLIT', 'Split'), ('STOCK_DIVIDEND', 'Stock Dividend'), ('CASH_DIVIDEND', 'Cash Dividend')])),
        migrations.AlterUniqueTogether('pricehistory', set()),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(forward, backward)],
            state_operations=[migrations.RemoveField('pricehistory', 'id'),
                              migrations.AddField('pricehistory', 'pk', models.CompositePrimaryKey('security', 'date', blank=True, editable=False, primary_key=True, serialize=False))],
        ),
        migrations.AddConstraint('corporateaction', models.CheckConstraint(condition=models.Q(action_type__in=['SPLIT', 'STOCK_DIVIDEND', 'CASH_DIVIDEND']), name='corporate_actions_type_check')),
    ]
