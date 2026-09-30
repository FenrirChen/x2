"""Stable current gift-package recommendations, with whitelisted local banners."""
import json
from importlib.resources import files
from x2server.messages.economy import GIFT_PACKAGE_DATA
from x2server.protocol.protobuf import ProtoSchema as S, ProtoField as F, FieldKind as K

HOT_AREA = S("HotAreaParam", tuple(F(n, name, K.INT32) for n, name in enumerate(("wide", "high", "xcoordinate", "ycoordinate", "jumpId"), 1)))
TAG = S("RecommendTag", (F(1, "showType", K.INT32), F(2, "startTime", K.INT64), F(3, "endTime", K.INT64),
    F(4, "order", K.INT32), F(5, "type", K.INT32), F(6, "hotAreaParam", K.MESSAGE, repeated=True),
    F(7, "cdnLinkPic", K.STRING), F(8, "name", K.STRING), F(9, "pos", K.INT32), F(10, "tag", K.INT32)))


def banner_response(method, path):
    from x2server.bootstrap.service import HTTPResponse
    catalog = json.loads(files("x2server").joinpath("data/recommendations.json").read_text(encoding="utf-8"))
    allowed = {"/" + row["image"]: row["image"] for row in catalog.values()}
    if path not in allowed or method.upper() != "GET":
        return HTTPResponse(404, "application/json", b'{}')
    return HTTPResponse(200, "image/png", files("x2server").joinpath("data/" + allowed[path]).read_bytes())


def recommend(economy, player):
    from .gift_packages import GiftPackageService
    from x2server.config.deployment import DeploymentEndpoints
    gifts = GiftPackageService(economy.store, economy)
    catalog = json.loads(files("x2server").joinpath("data/recommendations.json").read_text(encoding="utf-8"))
    endpoint = DeploymentEndpoints.from_environment()
    tags = []
    for raw in gifts.listing(player):
        status = GIFT_PACKAGE_DATA.decode(raw)
        package = gifts.packages[status["id"]]
        row = catalog.get(str(status["id"]))
        if not row or status["state"] != 0 or package["GiftPackageType"]["value"] == 2:
            continue
        tags.append(TAG.encode({"name": row["name"], "pos": len(tags),
            "cdnLinkPic": f"http://{endpoint.public_host}:{endpoint.http_port}/{row['image']}",
            "hotAreaParam": [HOT_AREA.encode({"wide": 860, "high": 500, "xcoordinate": 0, "ycoordinate": 0, "jumpId": row["jumpId"]})]}))
        if len(tags) == 6:
            break
    return {"code": 10, "recommendTag": tags}
