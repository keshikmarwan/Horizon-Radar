from types import SimpleNamespace

from app.services.matching_v2_service import _passes_hard_filters


def _topic(**kwargs):
    base = {
        'cluster': 'CL1',
        'action_type': 'RIA',
        'trl_min': 5,
        'trl_max': 7,
        'budget_total': 2_000_000,
        'metadata_json': {'procedure_stage': 'single-stage', 'compliance_flags': ['eligibility', 'ethics']},
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _profile(constraints: dict):
    return SimpleNamespace(constraints=constraints)


def test_hard_filters_pass_with_matching_constraints():
    profile = _profile(
        {
            'preferred_clusters': ['CL1'],
            'preferred_actions': ['RIA'],
            'preferred_trl': 6,
            'required_stage_type': 'single-stage',
            'required_compliance_flags': ['eligibility'],
        }
    )
    topic = _topic()

    result = _passes_hard_filters(profile, topic)
    assert result.passed is True
    assert result.reasons == []


def test_hard_filters_fail_for_multiple_conflicts():
    profile = _profile(
        {
            'preferred_clusters': ['CL4'],
            'preferred_actions': ['IA'],
            'preferred_trl': 3,
            'required_stage_type': 'two-stage',
            'forbidden_compliance_flags': ['ethics'],
            'max_budget_total': 1_000_000,
        }
    )
    topic = _topic()

    result = _passes_hard_filters(profile, topic)
    assert result.passed is False
    assert len(result.reasons) >= 4
