"""Observed and reanalysis climate data for the model sites.

    himsim.climate.record      ClimateRecord: a monthly temperature + precipitation series with provenance
    himsim.climate.openmeteo   download ERA5 / ERA5-Land from the free Open-Meteo archive API
    himsim.climate.kyanjin     the Kyanjin Gompa (Langtang, 3862 m) reference record used for Yala Glacier
"""

from himsim.climate.record import ClimateRecord

__all__ = ["ClimateRecord"]
