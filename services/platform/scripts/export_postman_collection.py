from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "platform" / "src"
if str(SRC) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SRC))

from alos.main import app  # noqa: E402

TARGET_DIR = ROOT / "docs" / "postman"
TARGET_FILE = TARGET_DIR / "ALOS-API.postman_collection.json"


def resolve_schema(schema: dict[str, Any] | None, spec: dict[str, Any]) -> dict[str, Any] | None:
    if not schema:
        return None
    reference = schema.get("$ref")
    if not reference or not reference.startswith("#/components/"):
        return schema
    resolved: Any = spec
    for segment in reference.removeprefix("#/").split("/"):
        resolved = resolved.get(segment, {})
    return resolved if isinstance(resolved, dict) else None


def json_example(schema: dict[str, Any] | None, spec: dict[str, Any]) -> Any:
    schema = resolve_schema(schema, spec)
    if not schema:
        return None

    schema_type = schema.get("type")
    if schema_type == "object":
        props = schema.get("properties", {})
        example: dict[str, Any] = {}
        for key, value in props.items():
            example[key] = json_example(value, spec)
        if not example and schema.get("title"):
            return {"value": schema.get("title")}
        return example

    if schema_type == "array":
        item_schema = schema.get("items", {})
        return [json_example(item_schema, spec)]

    if schema_type == "string":
        format_name = schema.get("format")
        if format_name == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if format_name == "date-time":
            return "2026-09-15T00:00:00Z"
        if format_name == "date":
            return "2026-09-15"
        enum_values = schema.get("enum")
        if enum_values:
            return enum_values[0]
        return schema.get("title") or "string"

    if schema_type == "integer":
        return 1

    if schema_type == "number":
        return 1.5

    if schema_type == "boolean":
        return True

    if schema_type == "null":
        return None

    if "anyOf" in schema:
        return json_example(schema["anyOf"][0], spec)

    if "oneOf" in schema:
        return json_example(schema["oneOf"][0], spec)

    return schema.get("default")


def request_body_for(operation: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if not request_body:
        return None

    content = request_body.get("content", {})
    if not content:
        return None

    body_cfg: dict[str, Any] = {}
    for content_type, media in content.items():
        schema = media.get("schema")
        example = media.get("example")
        if example is not None:
            body_cfg = {"mode": "raw", "raw": json.dumps(example, indent=2), "options": {"raw": {"language": "json"}}}
            break

        if schema:
            body_cfg = {
                "mode": "raw",
                "raw": json.dumps(json_example(schema, spec), indent=2),
                "options": {"raw": {"language": "json"}},
            }
            break

        if content_type.startswith("application/x-www-form-urlencoded"):
            body_cfg = {"mode": "urlencoded", "urlencoded": []}
            break

        if content_type.startswith("multipart/form-data"):
            body_cfg = {"mode": "formdata", "formdata": []}
            break

    return body_cfg or {"mode": "raw", "raw": "{}", "options": {"raw": {"language": "json"}}}


def build_postman_collection() -> dict[str, Any]:
    spec = app.openapi()
    collection = {
        "info": {
            "name": "ALOS API",
            "description": "Postman collection generated from the FastAPI OpenAPI schema.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "version": "1.0.0",
        },
        "item": [],
        "variable": [{"key": "baseUrl", "value": "http://localhost:8000", "type": "string"}],
    }

    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue

            summary = operation.get("summary") or operation.get("operationId") or f"{method.upper()} {path}"
            description = operation.get("description") or ""
            parameters = operation.get("parameters", [])
            request_body = request_body_for(operation, spec)

            url_path = path.strip("/").split("/")
            for index, segment in enumerate(url_path):
                if segment.startswith("{") and segment.endswith("}"):
                    url_path[index] = f":{segment.strip('{}')}"

            url = {
                "raw": "{{baseUrl}}/" + "/".join(url_path),
                "host": ["{{baseUrl}}"],
                "path": [part for part in path.split("/") if part],
            }

            query_params = []
            for param in parameters:
                if param.get("in") == "query":
                    query_params.append({
                        "key": param["name"],
                        "value": json_example(param.get("schema"), spec),
                        "description": param.get("description", ""),
                    })

            header_params = []
            for param in parameters:
                if param.get("in") == "header":
                    header_params.append({
                        "key": param["name"],
                        "value": json_example(param.get("schema"), spec),
                        "description": param.get("description", ""),
                    })

            item = {
                "name": summary,
                "description": description,
                "request": {
                    "method": method.upper(),
                    "header": header_params,
                    "body": request_body,
                    "url": url,
                },
                "response": [],
            }

            if query_params:
                item["request"]["url"]["query"] = query_params

            collection["item"].append(item)

    return collection


if __name__ == "__main__":
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    collection = build_postman_collection()
    TARGET_FILE.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated Postman collection: {TARGET_FILE}")
    print(f"Routes: {len(collection['item'])}")
