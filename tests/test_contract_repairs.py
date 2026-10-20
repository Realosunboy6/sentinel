"""Regressions for the M0–M3 audit. Synthetic data appears only in explicit mocks."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest
from django.core.management import call_command
from django.db import connection, transaction, IntegrityError

from apps.analysis import analyzer
from apps.analysis.charts import monthly_heatmap_chart
from apps.analysis.engine import run_analysis, run_risklens, _frontier
from apps.analysis.models import Analysis, AnalysisResult, Preset
from apps.marketdata.ingestion import ingest_security
from apps.marketdata.models import CorporateAction, PriceHistory, Security
from apps.marketdata.sources import YahooPriceSource, UnknownTickerError

FIXTURES = Path(__file__).parent / 'fixtures'
SYMBOLS = ['MCK', 'LLY', 'PWR', 'NVDA', 'STX']
WEIGHTS = [.2998, .2355, .1906, .1561, .118]
HOLDINGS = [{'symbol': s, 'weight': w} for s, w in zip(SYMBOLS, WEIGHTS)]


@pytest.fixture
def cached_prices(db):
    prices = pd.read_csv(FIXTURES / 'k5_prices.csv', index_col='date', parse_dates=True).iloc[:90]
    for symbol in prices:
        security = Security.objects.create(symbol=symbol)
        PriceHistory.objects.bulk_create([PriceHistory(security=security, date=day.date(), close=Decimal(str(value)), adj_close=Decimal(str(value))) for day, value in prices[symbol].items()])
    return prices


def test_validate_uses_available_history_not_year_2000():
    source = YahooPriceSource()
    with patch.object(source, 'fetch', return_value=pd.DataFrame({'adj_close': [100.0]})) as fetch:
        assert source.validate('MODERN')
    assert fetch.call_args.args[1] is None


@pytest.mark.django_db
def test_actions_atomic_ingestion_and_revision_expiry():
    # Explicit synthetic source fixture with one dividend and split.
    raw = pd.DataFrame({'Close': [100., 101.], 'Adj Close': [99., 101.], 'Dividends': [1., 0.], 'Stock Splits': [0., 2.]}, index=pd.date_range('2021-01-04', periods=2))
    with patch('yfinance.download', return_value=raw) as download:
        cleaned = YahooPriceSource().fetch('ACTION', date(2021, 1, 4), date(2021, 1, 5))
    assert download.call_args.kwargs['end'] == '2021-01-06'
    source = Mock(validate=Mock(return_value=True), fetch=Mock(return_value=cleaned))
    # Half-tick rounding must not create a false revision on every refresh.
    cleaned.loc[date(2021, 1, 4), 'adj_close'] = 99.00005
    security = ingest_security('ACTION', source)
    AnalysisResult.objects.create(input_hash='unchanged', data_asof=date(2021, 1, 5), metrics={'keep': True})
    ingest_security('ACTION', source)
    assert AnalysisResult.objects.filter(input_hash='unchanged').exists()
    assert PriceHistory.objects.get(security=security, date=date(2021, 1, 4)).adj_close == Decimal('99.0001')
    assert CorporateAction.objects.filter(security=security).count() == 2
    assert CorporateAction.objects.get(security=security, action_type='SPLIT').ratio == 2
    AnalysisResult.objects.create(input_hash='revision', data_asof=date(2021, 1, 5), metrics={'old': True})
    cleaned.loc[date(2021, 1, 4), 'adj_close'] = 90
    ingest_security('ACTION', source)
    assert not AnalysisResult.objects.exists()
    source.fetch.side_effect = UnknownTickerError('history failed')
    with pytest.raises(UnknownTickerError):
        ingest_security('FAILED', source)
    assert not Security.objects.filter(symbol='FAILED').exists()


@pytest.mark.django_db
def test_refresh_unions_tracked_and_explicit_symbols():
    Security.objects.create(symbol='TRACKED')
    with patch('apps.marketdata.management.commands.refresh_prices.ingest_security') as ingest:
        call_command('refresh_prices', symbols=['NEW', 'TRACKED'])
    assert sorted(c.args[0] for c in ingest.call_args_list) == ['NEW', 'TRACKED']


def test_hash_normalizes_equivalent_inputs():
    a = [{'symbol': 'A', 'weight': .6}, {'symbol': 'B', 'weight': .4}]
    b = [{'symbol': 'A', 'weight': .5988}, {'symbol': 'B', 'weight': .3992}]
    assert analyzer.canonicalize(a, date(2021, 1, 1), date(2026, 1, 1), 'SPY') == analyzer.canonicalize(b, date(2021, 1, 1), date(2026, 1, 1), 'SPY')


@pytest.mark.django_db
def test_normalize_post_preserves_dates_and_rejects_zero(client):
    data = {'action': 'normalize', 'holdings_json': json.dumps([{'symbol': 'SPY', 'weight': 50}]), 'start_date': '2021-01-04', 'end_date': '2023-01-04', 'benchmark': 'SPY'}
    response = client.post('/analyze', data)
    form = response.context['form']
    assert json.loads(form.initial['holdings_json'])[0]['weight'] == 100
    assert str(form.initial['end_date']) == '2023-01-04'
    data['holdings_json'] = json.dumps([{'symbol': 'SPY', 'weight': 0}])
    assert client.post('/analyze', data).context['form'].errors


def test_cache_recomputes_after_same_date_price_revision(cached_prices):
    start, end = cached_prices.index[0].date(), cached_prices.index[-1].date()
    with patch.object(analyzer, 'run_analysis', return_value={'version': 1}) as engine:
        analysis, _ = analyzer.analyze(HOLDINGS, start, end)
        analyzer.analyze(HOLDINGS, start, end)
        assert engine.call_count == 1
        PriceHistory.objects.filter(security__symbol='MCK', date=start).update(adj_close=80)
        engine.return_value = {'version': 2}
        _, metrics = analyzer.analyze(HOLDINGS, start, end)
        assert metrics['version'] == 2
        assert engine.call_count == 2
        assert Analysis.objects.filter(slug=analysis.slug).exists()


@pytest.mark.django_db(transaction=True)
def test_postgres_simultaneous_cache_fills_are_serialized(cached_prices):
    if connection.vendor != 'postgresql':
        pytest.skip('Production row-lock concurrency is PostgreSQL-specific')
    from concurrent.futures import ThreadPoolExecutor
    from django.db import connections
    from threading import Barrier
    barrier = Barrier(2)
    start, end = cached_prices.index[0].date(), cached_prices.index[-1].date()

    def submit():
        try:
            barrier.wait(timeout=10)
            analysis, metrics = analyzer.analyze(HOLDINGS, start, end)
            return analysis.slug, metrics['version']
        finally:
            connections.close_all()

    with patch.object(analyzer, 'run_analysis', return_value={'version': 'same-input'}) as engine:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    assert engine.call_count == 1
    assert AnalysisResult.objects.count() == 1


@pytest.mark.django_db
def test_uncached_requests_never_fetch_and_store_nothing(client):
    with patch('apps.marketdata.sources.YahooPriceSource.fetch', side_effect=AssertionError('No request-time downloads')):
        response = client.post('/analyze', {'holdings_json': '[{"symbol":"UNCACHED","weight":100}]', 'start_date': '2021-01-01', 'end_date': '2023-01-01'})
    assert response.status_code == 200
    assert 'No cached ticker' in response.content.decode()
    assert not Security.objects.exists()
    assert not Analysis.objects.exists()


def test_stale_and_empty_holdings_disclosed(cached_prices):
    start, end = cached_prices.index[0].date(), cached_prices.index[-1].date()
    PriceHistory.objects.filter(security__symbol='MCK', date__gt=cached_prices.index[10].date()).delete()
    Security.objects.create(symbol='EMPTY')
    holdings, prices, warnings = analyzer.prepare_prices([{'symbol': 'MCK', 'weight': .3}, {'symbol': 'EMPTY', 'weight': .2}, {'symbol': 'SPY', 'weight': .5}], start, end)
    assert holdings == [{'symbol': 'SPY', 'weight': 1.0}]
    assert prices.index[-1].date() == end
    assert 'MCK' in warnings[0] and 'EMPTY' in warnings[0] and 'renormalized' in warnings[0]


def test_long_interior_gap_is_not_a_daily_return(cached_prices):
    PriceHistory.objects.filter(security__symbol='MCK', date__gte=cached_prices.index[10].date(), date__lte=cached_prices.index[25].date()).delete()
    with pytest.raises(ValueError, match='gap longer'):
        analyzer.prepare_prices(HOLDINGS, cached_prices.index[0].date(), cached_prices.index[-1].date())


@pytest.mark.parametrize('length', [1, 2, 5, 8, 30])
def test_analyzer_young_history_json_safe(length):
    returns = pd.read_csv(FIXTURES / 'k5_prices.csv', index_col='date', parse_dates=True).pct_change().dropna().iloc[:length]
    metrics = run_analysis([{'symbol': 'SPY', 'weight': 1.}], returns[['SPY']], returns.SPY)
    assert metrics['young_history']
    if length < 8:
        assert metrics['jb_p'] is None
    json.dumps(metrics, allow_nan=False)


def test_frontier_dot_and_hill_use_consistent_definitions():
    import portlab.optimize as opt
    import portlab.risk.tail as tail
    returns = pd.read_csv(FIXTURES / 'k5_prices.csv', index_col='date', parse_dates=True).pct_change().dropna().iloc[:90]
    weights = np.array(WEIGHTS)
    frontier = _frontier(returns[SYMBOLS], weights, opt)
    assert frontier['portfolio']['return'] == pytest.approx(float(weights @ (returns[SYMBOLS].mean() * 252)), abs=1e-6)
    report = run_analysis(HOLDINGS, returns[SYMBOLS], returns.SPY)
    losses = -(returns[SYMBOLS] @ weights)
    assert report['hill'] == pytest.approx(tail.hill_estimator(losses, int(len(losses) ** .5))['xi'])
    assert report['regime'] in ('Calm', 'Stressed', 'Unknown')


def test_risk_one_return_and_es99():
    import portlab.risk.var as var
    returns = pd.read_csv(FIXTURES / 'spy_prices.csv', index_col='date', parse_dates=True).SPY.pct_change().dropna().iloc[:30]
    negative = returns[returns < 0].iloc[:2]
    assert run_risklens(negative)['tail']['hill'] is None
    young = run_risklens(returns.iloc[:1])
    assert young['es99'] is None and young['backtest']['young_history']
    json.dumps(young, allow_nan=False)
    report = run_risklens(returns)
    assert report['es99'] == pytest.approx(var.expected_shortfall(returns, alpha=.01, window=len(returns)-1).iloc[-1])


def test_monthly_has_compounded_annual_column():
    payload = monthly_heatmap_chart([{'year': 2021, 'month': 1, 'value': .1}, {'year': 2021, 'month': 2, 'value': -.1}], '2021-02-28')
    assert payload['xAxis']['data'][-1] == 'Annual'
    assert payload['series'][0]['data'][-1] == [12, 0, -1.0]


@pytest.mark.django_db
def test_landing_has_no_fabricated_fallback_or_unrelated_k5(client):
    Preset.objects.create(slug='k5-sample', name='K5', inputs={'holdings': HOLDINGS})
    AnalysisResult.objects.create(input_hash='not-k5', data_asof=date(2026, 10, 16), metrics={'portfolio': {'end': 999999}})
    response = client.get('/')
    assert response.context['k5_metrics'] is None
    assert '24,324' not in response.content.decode()
    assert '<svg' not in response.content.decode()


def test_api_and_risk_editor_through_real_cached_prices(client, cached_prices):
    data = {'holdings': [{'symbol': 'SPY', 'weight': 100}], 'benchmark': 'SPY', 'start_date': str(cached_prices.index[0].date()), 'end_date': str(cached_prices.index[20].date())}
    with patch('apps.marketdata.sources.YahooPriceSource.fetch', side_effect=AssertionError('No network')):
        response = client.post('/api/analyze', json.dumps(data), content_type='application/json')
        assert response.status_code == 200, response.content
        body = response.json()
        assert body['charts']['allocation']['series']
        shared = client.get(body['share_url'])
        assert shared.status_code == 200
        assert 'growth-scale' in shared.content.decode()
        form_data = {**data, 'holdings_json': json.dumps(data['holdings'])}
        form_data.pop('holdings')
        changed = client.post('/risk', form_data)
        assert changed.status_code == 302
        risk = client.get(changed['Location'])
        assert risk.status_code == 200
        assert 'data-portfolio-form' in risk.content.decode()
        assert 'ES 99%' in risk.content.decode()


def test_one_return_renders_through_api_share_and_risk(client, cached_prices):
    response = client.post('/api/analyze', json.dumps({'holdings': [{'symbol': 'SPY', 'weight': 100}],
        'benchmark': 'SPY', 'start_date': str(cached_prices.index[0].date()),
        'end_date': str(cached_prices.index[1].date())}), content_type='application/json')
    assert response.status_code == 200, response.content
    assert response.json()['metrics']['portfolio']['vol'] is None
    shared = client.get(response.json()['share_url'])
    assert shared.status_code == 200
    assert 'Short history' in shared.content.decode()
    risk = client.get('/risk', {'slug': response.json()['slug']})
    assert risk.status_code == 200
    assert 'VaR and ES estimates need at least two daily returns' in risk.content.decode()
    assert 'NaN' not in risk.context['charts_json']


@pytest.mark.django_db
def test_locked_schema_keys_and_action_check():
    assert Security._meta.db_table == 'securities'
    assert PriceHistory._meta.pk.field_names == ('security', 'date')
    assert AnalysisResult._meta.pk.field_names == ('input_hash', 'data_asof')
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, 'price_history')
    assert any(c['primary_key'] and set(c['columns']) == {'security_id', 'date'} for c in constraints.values())
    security = Security.objects.create(symbol='CHECK')
    with pytest.raises(IntegrityError), transaction.atomic():
        CorporateAction.objects.create(security=security, ex_date=date(2021, 1, 1), action_type='INVALID', ratio=1)


@pytest.mark.django_db(transaction=True)
def test_schema_upgrade_preserves_prices_actions_presets_and_share_links():
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    old = [('marketdata', '0001_initial'), ('analysis', '0001_initial')]
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        security = apps.get_model('marketdata', 'Security').objects.create(symbol='PRESERVE')
        apps.get_model('marketdata', 'PriceHistory').objects.create(security=security, date=date(2021, 1, 1), close=100, adj_close=99)
        apps.get_model('marketdata', 'CorporateAction').objects.create(security=security, ex_date=date(2021, 1, 1), action_type='CASH_DIVIDEND', ratio=1)
        apps.get_model('analysis', 'Preset').objects.create(slug='preserve', name='Preserve', inputs={'holdings': []})
        analysis = apps.get_model('analysis', 'Analysis').objects.create(slug='preserve-link', input_hash='preserve', inputs={'holdings': []}, engine_version='0.2.2')
        apps.get_model('analysis', 'AnalysisResult').objects.create(input_hash='preserve', data_asof=date(2021, 1, 1), metrics={'value': 99})
        MigrationExecutor(connection).migrate(leaves)
        assert PriceHistory.objects.get(pk=(security.pk, date(2021, 1, 1))).adj_close == 99
        assert CorporateAction.objects.get(security_id=security.pk).ratio == 1
        assert Preset.objects.get(pk='preserve').name == 'Preserve'
        assert Analysis.objects.get(slug='preserve-link').pk == analysis.pk
        assert AnalysisResult.objects.get(pk=('preserve', date(2021, 1, 1))).metrics == {'value': 99}
    finally:
        MigrationExecutor(connection).migrate(leaves)
