import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.api import routes
from app.services.horizon_matcher.engine import HorizonMatcherError
from app.services.horizon_matcher.scorer import AHPScorer, HybridAHPLPGurobiScorer, calculate_reliability_fit


class FakeExpr:
    def __init__(self, terms=None):
        self.terms = terms or []

    def __add__(self, other):
        if isinstance(other, FakeExpr):
            return FakeExpr(self.terms + other.terms)
        return FakeExpr(self.terms)

    __radd__ = __add__


class FakeVar:
    def __init__(self, ub, name):
        self.ub = ub
        self.name = name
        self.X = 0.0

    def __rmul__(self, coeff):
        return FakeExpr([(float(coeff), self)])

    def __le__(self, other):
        return ("<=", self, float(other))


class FakeGRB:
    OPTIMAL = 2
    MAXIMIZE = 1
    statusDict = {OPTIMAL: "Optimal"}


class FakeModel:
    def __init__(self, _name):
        self.vars = []
        self.constraints = []
        self.status = None
        self.ObjVal = 0.0
        self.objective = FakeExpr()

    def setParam(self, *_args, **_kwargs):
        return None

    def addVar(self, lb, ub, name):
        del lb
        var = FakeVar(ub=ub, name=name)
        self.vars.append(var)
        return var

    def setObjective(self, expr, _sense):
        self.objective = expr

    def addConstr(self, constraint, name):
        self.constraints.append((name, constraint))

    def optimize(self):
        caps = {}
        for _name, constraint in self.constraints:
            _op, var, rhs = constraint
            caps[var.name] = min(caps.get(var.name, var.ub), rhs)
        for var in self.vars:
            var.X = min(var.ub, caps.get(var.name, var.ub))
        self.ObjVal = sum(coeff * var.X for coeff, var in self.objective.terms)
        self.status = FakeGRB.OPTIMAL


class FakeGP:
    GRB = FakeGRB

    @staticmethod
    def Model(name):
        return FakeModel(name)


class AHPAndLPSolverTests(unittest.TestCase):
    def test_ahp_default_weights_and_consistency(self):
        scorer = AHPScorer()
        self.assertAlmostEqual(float(sum(scorer.weights)), 1.0, places=5)
        self.assertGreaterEqual(float(scorer.cr), 0.0)
        self.assertEqual(scorer.weights.shape[0], 4)

    @patch("app.services.horizon_matcher.scorer.gp", FakeGP)
    @patch("app.services.horizon_matcher.scorer.GRB", FakeGRB)
    def test_lp_without_constraints_uses_upper_bounds(self):
        scorer = HybridAHPLPGurobiScorer()
        result = scorer.solve_lp(
            local_scores={"excellence": 0.8, "impact": 0.7, "implementation": 0.6, "tech_fit": 0.5},
            hard_constraints={"budget_company_available": 999999999, "budget_max": 0},
        )
        self.assertEqual(result["status"], "Optimal")
        self.assertAlmostEqual(result["optimal_contributions"]["implementation"], 0.6, places=4)
        self.assertAlmostEqual(
            result["fit_score"],
            sum(result["breakdown"].values()),
            places=3,
        )

    @patch("app.services.horizon_matcher.scorer.gp", FakeGP)
    @patch("app.services.horizon_matcher.scorer.GRB", FakeGRB)
    def test_lp_trl_budget_and_sme_constraints_apply_caps(self):
        scorer = HybridAHPLPGurobiScorer()
        result = scorer.solve_lp(
            local_scores={"excellence": 0.9, "impact": 0.9, "implementation": 0.9, "tech_fit": 0.9},
            hard_constraints={
                "trl_violation": True,
                "budget_company_available": 1000,
                "budget_max": 5000,
                "sme_required": True,
                "sme_ok": False,
            },
        )
        self.assertEqual(result["optimal_contributions"]["excellence"], 0.3)
        self.assertEqual(result["optimal_contributions"]["implementation"], 0.2)


class CalculateReliabilityFitTests(unittest.TestCase):
    @patch("app.services.horizon_matcher.scorer._load_embedding_model", return_value=object())
    @patch("app.services.horizon_matcher.scorer._compute_semantic_scores")
    @patch("app.services.horizon_matcher.scorer._compute_bm25_scores")
    @patch("app.services.horizon_matcher.scorer._compute_constraints_score")
    @patch("app.services.horizon_matcher.scorer._solve_hybrid_score")
    def test_calculate_reliability_fit_orders_by_fit_score(
        self,
        solve_mock,
        constraints_mock,
        bm25_mock,
        semantic_mock,
        _model_mock,
    ):
        calls = [
            {"id": "A", "title": "Call A", "cluster": "Security", "type_of_action": "RIA", "specific_conditions": {}},
            {"id": "B", "title": "Call B", "cluster": "Security", "type_of_action": "IA", "specific_conditions": {}},
        ]
        semantic_mock.return_value = {"A": (0.9, 0.7), "B": (0.4, 0.3)}
        bm25_mock.return_value = {"A": (0.8, True), "B": (0.2, False)}
        constraints_mock.side_effect = [(0.6, 0.7, 0.5), (0.2, 0.2, 0.2)]
        solve_mock.side_effect = [
            {
                "fit_score": 0.82,
                "fit_score_100": 82.0,
                "weights": {"excellence": 0.4, "impact": 0.3, "implementation": 0.2, "tech_fit": 0.1},
                "breakdown": {"excellence": 0.3, "impact": 0.25, "implementation": 0.17, "tech_fit": 0.1},
                "optimal_contributions": {"excellence": 0.75, "impact": 0.8, "implementation": 0.85, "tech_fit": 1.0},
                "status": "Optimal",
                "cr": 0.02,
                "consistency_ok": True,
                "constraints_applied": {},
                "solver": "Gurobi",
                "local_scores": {"excellence": 0.9, "impact": 0.8, "implementation": 0.6, "tech_fit": 0.7},
            },
            {
                "fit_score": 0.31,
                "fit_score_100": 31.0,
                "weights": {"excellence": 0.4, "impact": 0.3, "implementation": 0.2, "tech_fit": 0.1},
                "breakdown": {"excellence": 0.1, "impact": 0.11, "implementation": 0.07, "tech_fit": 0.03},
                "optimal_contributions": {"excellence": 0.25, "impact": 0.37, "implementation": 0.35, "tech_fit": 0.3},
                "status": "Optimal",
                "cr": 0.02,
                "consistency_ok": True,
                "constraints_applied": {},
                "solver": "Gurobi",
                "local_scores": {"excellence": 0.4, "impact": 0.25, "implementation": 0.2, "tech_fit": 0.3},
            },
        ]

        results = calculate_reliability_fit(
            company_profile={"mission": "", "technical_knowhow": "", "description": "", "keywords": []},
            calls=calls,
            faiss_index=object(),
            metadata={},
            config={},
        )

        self.assertEqual(results[0]["call_id"], "A")
        self.assertGreater(results[0]["fit_score"], results[1]["fit_score"])


class ScoreEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_score_endpoint_returns_new_shape(self):
        payload = {
            "generated_at": "2026-04-14T00:00:00Z",
            "top_n": 10,
            "total_calls": 1,
            "results": [{
                "call_id": "CALL-1",
                "title": "Title",
                "cluster": "Security",
                "type_of_action": "RIA",
                "fit_score": 0.75,
                "fit_score_100": 75.0,
                "score_breakdown": {
                    "fit_score": 0.75,
                    "fit_score_100": 75.0,
                    "weights": {"excellence": 0.4, "impact": 0.3, "implementation": 0.2, "tech_fit": 0.1},
                    "breakdown": {"excellence": 0.25, "impact": 0.24, "implementation": 0.16, "tech_fit": 0.1},
                    "optimal_contributions": {"excellence": 0.625, "impact": 0.8, "implementation": 0.8, "tech_fit": 1.0},
                    "status": "Optimal",
                    "cr": 0.02,
                    "consistency_ok": True,
                    "constraints_applied": {},
                    "solver": "Gurobi",
                    "local_scores": {"excellence": 0.8, "impact": 0.7, "implementation": 0.6, "tech_fit": 0.5},
                },
                "spider_axes": {},
                "justification": "Justification",
                "call_data": None,
            }],
            "other_results": [],
            "status": {"calls_json": True},
        }
        with patch.object(routes.horizon_matcher_engine, "score", return_value=payload):
            response = self.client.post(
                "/api/horizon-matcher/score",
                headers={"X-User-Id": "demo-user"},
                json={
                    "profile": {
                        "description": "desc",
                        "mission": "desc",
                        "technical_knowhow": "kw",
                        "keywords": ["kw"],
                        "trl_current": 5,
                        "budget_company_available": 1000,
                        "budget_max": None,
                        "is_sme": False,
                        "ssh_capacity": False,
                        "fair_compliant": False,
                        "gender_dimension_active": False,
                        "gender_balance_required": False,
                        "clusters_interest": ["Security"],
                    },
                    "top_n": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("fit_score", body["results"][0])
        self.assertIn("fit_score_100", body["results"][0]["score_breakdown"])
        self.assertNotIn("reliability_score", body["results"][0])

    def test_score_endpoint_surfaces_gurobi_error(self):
        with patch.object(
            routes.horizon_matcher_engine,
            "score",
            side_effect=HorizonMatcherError("Il motore AHP + Gurobi richiede licenza valida."),
        ):
            response = self.client.post(
                "/api/horizon-matcher/score",
                headers={"X-User-Id": "demo-user"},
                json={
                    "profile": {
                        "description": "desc",
                        "mission": "desc",
                        "technical_knowhow": "kw",
                        "keywords": ["kw"],
                        "trl_current": 5,
                        "budget_company_available": 1000,
                        "budget_max": None,
                        "is_sme": False,
                        "ssh_capacity": False,
                        "fair_compliant": False,
                        "gender_dimension_active": False,
                        "gender_balance_required": False,
                        "clusters_interest": ["Security"],
                    },
                    "top_n": 10,
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Gurobi", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
