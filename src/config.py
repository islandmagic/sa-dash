"""Source configuration for islands and providers."""

ISLANDS = {
    "kauai": {
        "name": "Kauai",
        "scrapers": [
            "weather_kauai",
            "propagation",
            "kiuc",
            #"hawaiiantelcom",
            "kauai_water",
            "hidot_highways_news",
            "usgs_water_levels",
            "kauai_now",
            "khon2_kauai",
            "cnn_topstories",
            "foxnews_us",
        ],
    }
}
