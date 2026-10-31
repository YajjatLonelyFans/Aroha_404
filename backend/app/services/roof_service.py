"""Roof assessment: traced outline (or manual dimensions) → usable area, panel layout, kWp range."""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.assumptions import Assumptions
from app.core.errors import NotFoundError
from app.db import collections as c
from app.db.store import DocumentStore
from app.domain.geometry import GeometryParams, assess_geometry, manual_geometry
from app.domain.layout import (
    CapacityParams,
    LayoutParams,
    ModuleSpec,
    assess_capacity,
    pack_panels,
    panels_to_geojson,
    winter_noon_sun_elevation_deg,
)
from app.domain.units import round_area_m2, round_kwp, round_pct
from app.schemas.roof import ConstraintOut, KwpRange, RoofAssessRequest, RoofAssessResponse
from app.services.weather_service import utc_now

MODEL_VERSION = "roof-1.0.0"


def facing(azimuth_deg: float) -> str:
    named = {0: "south", -90: "east", 90: "west", 180: "north", -180: "north"}
    return named.get(round(azimuth_deg), f"{azimuth_deg:g}° from south (0 = south, 90 = west)")


def inputs_hash(req: RoofAssessRequest, version: str) -> str:
    payload = req.model_dump(exclude={"user_id", "property_id"})
    raw = json.dumps({"inputs": payload, "assumptions": version}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class RoofService:
    def __init__(
        self, store: DocumentStore, assumptions: Assumptions, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._store = store
        self._a = assumptions
        self._clock = clock

    async def assess(self, req: RoofAssessRequest) -> RoofAssessResponse:
        prop = await self._store.get(c.PROPERTIES, req.property_id)
        if prop is None or prop["user_id"] != req.user_id:
            raise NotFoundError("Property")

        a = self._a
        module = ModuleSpec(a.require("module.length_m"), a.require("module.width_m"), a.require("module.wp"))
        setback = a.require("layout.edge_setback_m")
        sun_elevation = None
        if req.roof_type == "flat":
            tilt = a.require("layout.default_flat_tilt_deg")
            azimuth = a.require("layout.default_azimuth_deg")
            row_gap = a.require("layout.row_gap_m")
            # Rows on raised frames are spaced so they do not shade each other at noon
            # on the shortest day, worked out for this house's latitude.
            sun_elevation = winter_noon_sun_elevation_deg(prop["pin"]["coordinates"][1])
        else:
            tilt, azimuth = req.slope_tilt_deg, req.slope_azimuth_deg
            row_gap = a.require("layout.flush_gap_m")

        if req.outline is not None:
            clearance = a.require("layout.no_go_clearance_m")
            geom = assess_geometry(
                req.outline,
                [n.geometry for n in req.no_go_areas],
                GeometryParams(
                    edge_setback_m=setback,
                    no_go_clearance_m=clearance,
                    bbox=a.validation.delhi_bbox,
                    min_outline_m2=a.require("validation.min_outline_m2"),
                    max_outline_m2=a.require("validation.max_outline_m2"),
                ),
            )
        else:
            md = req.manual_dimensions
            geom = manual_geometry(md.length_m, md.width_m, md.no_go_areas_m2, setback)

        layout = pack_panels(geom.usable_m, module, LayoutParams(tilt, azimuth, row_gap, sun_elevation))
        capacity = assess_capacity(
            panel_count=layout.panel_count,
            module_wp=module.wp,
            shading=req.shading.model_dump(),
            roof_type=req.roof_type,
            azimuth_deg=azimuth,
            usable_area_m2=geom.usable_area_m2,
            outline_area_m2=geom.outline_area_m2,
            no_go_area_m2=geom.no_go_area_m2,
            traced=geom.georeferenced,
            params=CapacityParams(
                shading_by_level={
                    level: a.require(f"losses.shading_by_level.{level}") for level in ("none", "partial", "heavy")
                },
                shading_cap_fraction=a.require("losses.shading_cap_fraction"),
                shading_haircut_fraction=a.require("capacity.shading_haircut_fraction"),
                small_area_m2=a.require("capacity.small_area_m2"),
                many_obstructions_fraction=a.require("capacity.many_obstructions_fraction"),
            ),
        )

        gap_used = layout.row_gap_m if layout.row_gap_m is not None else row_gap
        spacing = f"{gap_used:.2f} m between rows"
        if sun_elevation is not None:
            spacing += f" so rows do not shade each other at noon on the shortest day (sun {sun_elevation:.0f}° high)"
        assumptions = [
            f"Panel {module.length_m} × {module.width_m} m, {module.wp:g} Wp (assumptions {a.version}).",
            f"{setback} m kept clear along the roof edge.",
            f"Panels tilted {tilt:g}° facing {facing(azimuth)}, {spacing}.",
            f"Shade lowers output by {round_pct(100 * capacity.shading_loss_fraction):g}%.",
        ]
        if req.outline is not None:
            assumptions.insert(2, f"{a.layout.no_go_clearance_m} m kept clear around tanks, stair rooms and heaters.")
        else:
            assumptions.append(
                "Manual dimensions: no-go areas are counted by size only, so the panel count is approximate."
            )

        now = self._clock()
        doc: dict[str, Any] = {
            "property_id": req.property_id,
            "user_id": req.user_id,
            "inputs_hash": inputs_hash(req, a.version),
            "outline_area_m2": round_area_m2(geom.outline_area_m2),
            "setback_area_m2": round_area_m2(geom.setback_area_m2),
            "no_go_area_m2": round_area_m2(geom.no_go_area_m2),
            "usable_area_m2": round_area_m2(geom.usable_area_m2),
            "panel_layout": panels_to_geojson(layout.panels_m) if geom.georeferenced else None,
            "panel_count": capacity.panel_count["likely"],
            "panel_count_range": capacity.panel_count,
            "module_wp": module.wp,
            "capacity_kwp": {k: round_kwp(v) for k, v in capacity.capacity_kwp.items()},
            "array_tilt_deg": float(tilt),
            "array_azimuth_deg": float(azimuth),
            "orientation": layout.orientation,
            "row_gap_m": None if layout.row_gap_m is None else round(layout.row_gap_m, 2),
            "shading_loss_fraction": capacity.shading_loss_fraction,
            "constraints": [{"code": x.code, "message": x.message} for x in capacity.constraints],
            "assumptions": assumptions,
            "confidence": capacity.confidence,
            "traced": geom.georeferenced,
            "roof_type": req.roof_type,
            "assumptions_version": a.version,
            "model_version": MODEL_VERSION,
            "created_at": now,
        }
        assessment_id = await self._store.insert(c.ROOF_ASSESSMENTS, doc)
        await self._store.update(c.PROPERTIES, req.property_id, {
            "outline": req.outline,
            "manual_dimensions": req.manual_dimensions.model_dump() if req.manual_dimensions else None,
            "no_go_areas": [n.model_dump() for n in req.no_go_areas],
            "roof_type": req.roof_type,
            "slope_tilt_deg": req.slope_tilt_deg,
            "slope_azimuth_deg": req.slope_azimuth_deg,
            "shading": req.shading.model_dump(),
            "updated_at": now,
        })

        return RoofAssessResponse(
            assessment_id=assessment_id,
            **{k: doc[k] for k in (
                "property_id", "outline_area_m2", "setback_area_m2", "no_go_area_m2", "usable_area_m2",
                "panel_layout", "panel_count", "module_wp", "array_tilt_deg", "array_azimuth_deg",
                "orientation", "row_gap_m", "shading_loss_fraction", "assumptions", "confidence", "traced",
                "assumptions_version", "model_version",
            )},
            capacity_kwp=KwpRange(**doc["capacity_kwp"]),
            constraints=[ConstraintOut(**x) for x in doc["constraints"]],
        )
