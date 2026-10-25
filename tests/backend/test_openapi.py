from scripts.export_openapi import TARGET, render


def test_versioned_openapi_matches_application():
    assert TARGET.read_text(encoding="utf-8") == render()


def test_errors_use_shared_contract():
    import yaml

    schema = yaml.safe_load(render())
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            for status, response in operation["responses"].items():
                if status.startswith(("4", "5")):
                    ref = response["content"]["application/json"]["schema"]["$ref"]
                    assert ref.endswith("/ToolError"), (method, path, status)
