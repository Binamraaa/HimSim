"""Field measurements a glacier model can be checked against.

Every ``Measurement`` is a number someone measured, with its source. ``validation.reality_check``
computes the model's equivalent and grades the match. The model is *calibrated* on one
number only (the average DEM thinning over the calibration period); every measurement
here is an independent test.

Grading rule (shown to students in the app):
- inside the stated uncertainty or range, or within 10 % when the source states none -> "matches"
- otherwise within 25 % of the measured value                                       -> "close"
- otherwise                                                                         -> "off"
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    what: str  # student-facing question, e.g. "How much ice was there in 2009?"
    kind: str  # how the model value is computed (see validation.MODEL_VALUES)
    value: float  # the measured value (or a range midpoint, see low/high)
    unit: str
    source: str  # short citation
    params: tuple = ()  # (key, value) pairs for the model calculation, e.g. (("year", 2009),)
    uncertainty: float | None = None  # ± stated by the source
    low: float | None = None  # a measured range (both ends), when the source gives one instead of ±
    high: float | None = None  # also used alone for an upper bound (then grading uses the 10 % rule)
    shown_as: str = ""  # how to print the measured value, if not just value + unit
    why_off: str = ""  # plain-language reason, shown when the model doesn't match

    @property
    def accepted(self) -> tuple[float, float] | None:
        if self.low is not None and self.high is not None:
            return self.low, self.high
        if self.uncertainty is not None:
            return self.value - self.uncertainty, self.value + self.uncertainty
        return None

    def grade(self, model: float) -> str:
        rng = self.accepted
        inside = rng[0] <= model <= rng[1] if rng is not None else abs(model - self.value) <= 0.10 * abs(self.value)
        if inside:
            return "matches"
        if abs(model - self.value) <= 0.25 * abs(self.value):
            return "close"
        return "off"


SUGIYAMA_2013 = ("Sugiyama et al. (2013), Annals of Glaciology 54(64), doi:10.3189/2013AoG64A111: "
                 "radar ice thickness and GPS survey, Oct-Nov 2009")
STUMM_2021 = ("Stumm et al. (2021), Earth System Science Data 13, 3791-3818, doi:10.5194/essd-13-3791-2021: "
              "ICIMOD stake measurements 2011-2017")

YALA_MEASUREMENTS: tuple[Measurement, ...] = (
    Measurement(
        "How much ice was in the glacier in 2009?", "volume", 0.061, "km³", SUGIYAMA_2013,
        params=(("year", 2009),), high=0.066, shown_as="0.061 km³ (upper bound 0.066)",
    ),
    Measurement(
        "How thick was the lower glacier (5120–5300 m) in 1982?", "centre_thickness", 60.0, "m", SUGIYAMA_2013,
        params=(("year", 1982), ("z_low", 5120.0), ("z_high", 5300.0)),
    ),
    Measurement(
        "… and in 1996?", "centre_thickness", 45.0, "m", SUGIYAMA_2013,
        params=(("year", 1996), ("z_low", 5120.0), ("z_high", 5300.0)),
    ),
    Measurement(
        "… and in 2009, measured with radar?", "centre_thickness", 31.0, "m", SUGIYAMA_2013,
        params=(("year", 2009), ("z_low", 5120.0), ("z_high", 5300.0)),
        uncertainty=1.5 + 0.02 * 31.0,  # stated radar error: 1.5 m + 2 % of the thickness
    ),
    Measurement(
        "Average yearly mass balance 2011–2017", "mass_balance", -0.80, "m w.e./yr", STUMM_2021,
        params=(("first", 2012), ("last", 2017)), uncertainty=0.28,
        # Hydrological years Nov 2011-Nov 2017 ≈ model calendar years 2012-2017.
    ),
    Measurement(
        "Average snowline (ELA) 2011–2017", "ela", 5449.0, "m", STUMM_2021,
        params=(("first", 2012), ("last", 2017)), low=5380.0, high=5518.0,
        shown_as="between 5380 and 5518 m",
    ),
    Measurement(
        "How fast melting increases going down the glacier (near the snowline)", "smb_gradient", 1.04,
        "m w.e. per 100 m", STUMM_2021, params=(("first", 2012), ("last", 2017)), uncertainty=0.12,
        why_off="The model uses monthly air temperature only. Real melt on the tongue is also driven by strong "
                "Himalayan sunshine and warm days within each month, so it rises faster toward the snout.",
    ),
    Measurement(
        "Glacier area in 2006 (satellite image)", "area", 1.82, "km²", SUGIYAMA_2013,
        params=(("year", 2006),),
        why_off="The model starts from the 2000 inventory outline, which includes steep snowy slopes that other "
                "maps leave out, and it counts any ice thicker than 1 m as glacier. Thin ice at the edges lingers.",
    ),
    Measurement(
        "Glacier area in 2012 (satellite image)", "area", 1.61, "km²", STUMM_2021,
        params=(("year", 2012),),
        why_off="Same reason as for 2006: the model's glacier edge is drawn differently from the satellite maps.",
    ),
)

# Yearly glacier-wide mass balance (m w.e.) with uncertainty, Stumm et al. (2021), Table 2 / Sect. 4.1.
# Keyed by the calendar year in which each Nov-Nov hydrological year ends.
YALA_YEARLY_MASS_BALANCE: dict[int, tuple[float, float]] = {
    2012: (-0.86, 0.40),
    2013: (-0.01, 0.29),
    2014: (-0.61, 0.27),
    2015: (-1.18, 0.26),
    2016: (-0.61, 0.23),
    2017: (-1.54, 0.20),
}
