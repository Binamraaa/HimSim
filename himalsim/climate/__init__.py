"""Observed and reanalysis climate data for the model sites.

    himalsim.climate.record      ClimateRecord: a monthly temperature + precipitation series with provenance
    himalsim.climate.openmeteo   download ERA5 / ERA5-Land from the free Open-Meteo archive API
    himalsim.climate.kyanjin     the Kyanjin Gompa (Langtang, 3862 m) reference record used for Yala Glacier
"""

from himalsim.climate.record import ClimateRecord

__all__ = ["ClimateRecord"]
