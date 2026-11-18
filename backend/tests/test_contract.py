import re
from pathlib import Path

from fastapi.routing import APIRoute

from backend.main import app

BACKEND = Path(__file__).parent.parent
HIDDEN = ("evals", "data/security")


def api_routes() -> list[APIRoute]:
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api")
    ]


def test_every_operation_has_an_id_and_a_one_line_docstring():
    for route in api_routes():
        assert route.operation_id, route.path
        docstring = (route.endpoint.__doc__ or "").strip()
        assert docstring, route.path
        assert "\n" not in docstring, route.path


def test_no_operation_has_an_optional_input():
    schema = app.openapi()
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            for parameter in operation.get("parameters", []):
                assert parameter["required"], (method, path, parameter["name"])
            body = operation.get("requestBody")
            if body:
                assert body["required"], (method, path)
                ref = body["content"]["application/json"]["schema"]["$ref"]
                model = schema["components"]["schemas"][ref.split("/")[-1]]
                assert set(model["properties"]) == set(model["required"]), path


def test_backend_never_reads_the_answer_key():
    for module in BACKEND.glob("*.py"):
        text = module.read_text(encoding="utf-8").lower()
        for name in HIDDEN:
            assert name not in text, (module.name, name)


def test_no_route_serves_hidden_files():
    for route in api_routes():
        assert not any(name in route.path for name in HIDDEN)


def test_the_backend_reads_only_the_files_it_serves():
    seed = (BACKEND / "seed.py").read_text(encoding="utf-8")
    assert set(re.findall(r'"(\w+\.(?:json|md))"', seed)) == {
        "claims.json",
        "policies.json",
        "customers.json",
        "plans.json",
        "handlers.json",
        "company.json",
        "policy_wording.md",
        "claims_manual.md",
        "instructions_queue.md",
        "instructions_claim.md",
    }
