"""Source configuration for islands and providers."""

ISLANDS = {
    "kauai": {
        "name": "Kauai",
        "scrapers": [
            "weather_kauai",
            "precipitation",
            "kiuc",
            "verizon_mobile",
            "att_mobile",
            #"hawaiiantelcom",
            "propagation",
            "kauai_water",
            "hidot_highways_news",
            "usgs_water_levels",
            "ocean_water_quality",
            "kauai_now",
            "khon2_kauai",
            "cnn_topstories",
            "foxnews_us",
        ],
    }
}
