def test_every_operation_follows_the_api_rules(client):
    schema = client.get("/openapi.json").json()
    models = schema["components"]["schemas"]
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            name = f"{method.upper()} {path}"
            assert operation.get("operationId"), name
            description = operation.get("description", "")
            assert description, name
            assert "\n" not in description, name
            for parameter in operation.get("parameters", []):
                assert parameter["required"], name
            if "requestBody" in operation:
                body = operation["requestBody"]
                assert body["required"], name
                ref = body["content"]["application/json"]["schema"]["$ref"]
                model = models[ref.split("/")[-1]]
                assert set(model["properties"]) == set(model["required"]), name
