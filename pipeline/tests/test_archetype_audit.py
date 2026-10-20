import numpy as np
import pytest
from gt.archetype_audit import THEMES, adjusted_rand, matrix_diagnostics
from gt.archetypes import METRIC_KEYS


def test_adjusted_rand_ignores_label_names_and_detects_disagreement():
    assert adjusted_rand(np.array([0,0,1,1]), np.array([8,8,4,4])) == 1
    assert adjusted_rand(np.array([0,0,1,1]), np.array([0,1,0,1])) == pytest.approx(-.5)
    assert adjusted_rand(np.zeros(4),np.zeros(4)) == 1
    with pytest.raises(ValueError):adjusted_rand(np.array([1]),np.array([1]))


def test_themes_cover_every_approved_feature_once():
    keys=[key for group in THEMES.values() for key in group]
    assert sorted(keys)==sorted(METRIC_KEYS)


def test_diagnostic_is_deterministic_and_reports_missingness_and_collinearity():
    rng=np.random.default_rng(8)
    values=rng.random((16,len(METRIC_KEYS)))
    values[:,1]=values[:,0]
    values[0,2]=np.nan
    first=matrix_diagnostics(values)
    assert first==matrix_diagnostics(values)
    assert first['model_persisted'] is False
    assert first['missing_by_metric']['gvi_ndvi_street']==1
    assert any(row['first']=='tree_canopy_pct' and row['second']=='canopy_height_m' and row['correlation']==pytest.approx(1) for row in first['strong_correlations_abs_ge_0_8'])
    assert sum(row['current_squared_distance_share'] for row in first['themes'])==pytest.approx(1)
    for experiment in first['experiments']:
        assert sum(experiment['cluster_sizes'])==16
        assert experiment['subsample_stability']['runs']==24


def test_audit_uses_read_only_transaction_and_never_commits(monkeypatch):
    from unittest.mock import MagicMock
    import gt.archetype_audit as audit
    import gt.archetypes as archetypes
    conn=MagicMock()
    monkeypatch.setattr(audit,'database_url',lambda:'test-only')
    monkeypatch.setattr(audit.psycopg,'connect',lambda *a,**k:conn)
    active=conn.__enter__.return_value
    monkeypatch.setattr(archetypes,'_load_district_matrix',lambda c:([1]*6,np.zeros((6,len(METRIC_KEYS))),{}))
    monkeypatch.setattr(audit,'matrix_diagnostics',lambda m:{'model_persisted':False})
    reports=[]
    monkeypatch.setattr(audit,'write_report',lambda report,name:reports.append(report) or name)
    audit.audit_archetypes()
    assert active.cursor.return_value.__enter__.return_value.execute.call_args_list[0].args[0]=='SET TRANSACTION READ ONLY'
    active.commit.assert_not_called()
    assert reports[0].promotable is False
