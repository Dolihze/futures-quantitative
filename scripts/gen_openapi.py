"""从 Flask 路由表 + backend/schemas.py 生成 OpenAPI 3.1 文档 -> openapi.json（项目根目录）。

用法：python scripts/gen_openapi.py [输出路径]
前端类型由它再生成：npm run api:types（见 package.json）。

只描述【响应】：请求参数仍由路由里的校验负责。schemas.RESPONSES 里登记的接口使用对应模型，
其余接口响应为通用 ApiResult。生成过程不读用户磁盘配置、不启动服务。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pydantic import TypeAdapter  # noqa: E402

from backend import schemas  # noqa: E402
from backend.app import app  # noqa: E402

REF_PREFIX = "#/components/schemas/"


def _strip_additional_properties(node):
    """去掉 pydantic 因 extra="allow" 生成的 additionalProperties: true。

    extra="allow" 只是让运行时校验（tests/test_contract.py）不因后端多返回字段而失败；
    留在 OpenAPI 里会让 openapi-typescript 给每个模型加 `[key: string]: unknown`，
    前端写错 / 用了已删除的字段也不会报错，等于没有契约。
    dict[str, Any] 之类的“开放对象”字段不受影响（它们的 additionalProperties 是 schema 而不是 true）。
    """
    if isinstance(node, dict):
        if node.get("additionalProperties") is True and "properties" in node:
            del node["additionalProperties"]
        for v in node.values():
            _strip_additional_properties(v)
    elif isinstance(node, list):
        for v in node:
            _strip_additional_properties(v)
    return node


def _schema_for(model_cls, many):
    """返回 (引用或内联 schema, 需要登记的 $defs)。"""
    adapter = TypeAdapter(list[model_cls] if many else model_cls)
    sch = adapter.json_schema(ref_template=REF_PREFIX + "{model}")
    defs = sch.pop("$defs", {})
    return _strip_additional_properties(sch), _strip_additional_properties(defs)


def _flask_rule_to_openapi(rule):
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def build():
    components = {}
    paths = {}
    # 实际返回数组而不是对象的接口
    returns_list = {("GET", "/api/brokers")}

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.endpoint == "static" or not rule.rule.startswith("/api/"):
            continue
        view = app.view_functions[rule.endpoint]
        doc = (view.__doc__ or "").strip()
        summary = doc.splitlines()[0] if doc else rule.endpoint
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            model = schemas.RESPONSES.get((method, rule.rule), schemas.ApiResult)
            many = (method, rule.rule) in returns_list
            sch, defs = _schema_for(model, many)
            components.update(defs)
            if many:
                # 数组 schema 的 items 是内联展开的：登记元素模型，响应引用数组
                item_name = model.__name__
                item_schema, item_defs = _schema_for(model, False)
                components.update(item_defs)
                components.setdefault(item_name, item_schema)
                sch = {"type": "array", "items": {"$ref": REF_PREFIX + item_name}}
            elif "$ref" not in sch:
                components.setdefault(model.__name__, sch)
                sch = {"$ref": REF_PREFIX + model.__name__}
            paths.setdefault(_flask_rule_to_openapi(rule.rule), {})[method.lower()] = {
                "operationId": f"{method.lower()}_{rule.endpoint.replace('.', '_')}",
                "summary": summary,
                "tags": [rule.endpoint.split(".")[0]],
                "responses": {
                    "200": {"description": "成功", "content": {"application/json": {"schema": sch}}},
                    "default": {
                        "description": "失败：success=false + message（HTTP 4xx/5xx）",
                        "content": {"application/json": {"schema": {"$ref": REF_PREFIX + "ApiResult"}}},
                    },
                },
            }
    if "ApiResult" not in components:
        s, d = _schema_for(schemas.ApiResult, False)
        components.update(d)
        components["ApiResult"] = s

    return {
        "openapi": "3.1.0",
        "info": {"title": "期货量化交易系统 后端接口", "version": "1.0.0",
                 "description": "由 scripts/gen_openapi.py 生成，勿手改。字段以 backend/schemas.py 为准。"},
        "paths": dict(sorted(paths.items())),
        "components": {"schemas": dict(sorted(components.items()))},
    }


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "openapi.json")
    doc = build()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    print(f"[openapi] {len(doc['paths'])} 个路径, {len(doc['components']['schemas'])} 个模型 -> {out}")


if __name__ == "__main__":
    main()
