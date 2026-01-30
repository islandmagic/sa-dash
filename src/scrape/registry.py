from src.scrape.hawaiiantelcom import scrape as scrape_hawaiiantelcom
from src.scrape.hidot_highways_news import scrape as scrape_hidot_highways_news
from src.scrape.khon2_kauai import scrape as scrape_khon2_kauai
from src.scrape.kauai_now import scrape as scrape_kauai_now
from src.scrape.kauai_water import scrape as scrape_kauai_water
from src.scrape.kiuc import scrape as scrape_kiuc
from src.scrape.cnn_topstories import scrape as scrape_cnn_topstories
from src.scrape.foxnews_us import scrape as scrape_foxnews_us
from src.scrape.weather_kauai import scrape as scrape_weather_kauai
from src.scrape.usgs_water_levels import scrape as scrape_usgs_water_levels


SCRAPERS = {
    "cnn_topstories": scrape_cnn_topstories,
    "foxnews_us": scrape_foxnews_us,
    "hawaiiantelcom": scrape_hawaiiantelcom,
    "hidot_highways_news": scrape_hidot_highways_news,
    "kauai_now": scrape_kauai_now,
    "khon2_kauai": scrape_khon2_kauai,
    "kauai_water": scrape_kauai_water,
    "kiuc": scrape_kiuc,
    "weather_kauai": scrape_weather_kauai,
    "usgs_water_levels": scrape_usgs_water_levels,
}


def get_scraper(name: str):
    if name not in SCRAPERS:
        raise KeyError(f"Unknown scraper: {name}")
    return SCRAPERS[name]
