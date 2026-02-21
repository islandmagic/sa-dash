"""Source configuration for islands and providers."""

ISLANDS = {
    "kauai": {
        "name": "Kauai",
        "scrapers": [
            "weather_kauai",
            "precipitation",
            "kiuc",
            "kauai_water",
            "verizon_mobile",
            "att_mobile",
            "propagation",
            "hidot_highways_news",
            "usgs_water_levels",
            "ocean_water_quality",
            "adsbexchange_live",
            "marinetraffic_kauai",
            "kauai_county_press",
            "kauai_now",
        ],
    }
}
