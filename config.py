import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    MAX_BOT_TOKEN: str
    YANDEX_DISK_TOKEN: str
    YANDEX_DISK_TEMPLATE_PATH: str
    YANDEX_DISK_NOMENCLATURE_PATH: str
    YANDEX_DISK_GENERATED_FOLDER: str
    DATABASE_PATH: str
    PORT: int
    WEBHOOK_URL: str


config = Config(
    MAX_BOT_TOKEN=os.getenv("MAX_BOT_TOKEN", ""),
    YANDEX_DISK_TOKEN=os.getenv("YANDEX_DISK_TOKEN", ""),
    YANDEX_DISK_TEMPLATE_PATH=os.getenv("YANDEX_DISK_TEMPLATE_PATH", "/MFB/templates/kp_template_v2.xlsx"),
    YANDEX_DISK_NOMENCLATURE_PATH=os.getenv("YANDEX_DISK_NOMENCLATURE_PATH", "/MFB/data/nomenclature.xlsx"),
    YANDEX_DISK_GENERATED_FOLDER=os.getenv("YANDEX_DISK_GENERATED_FOLDER", "/MFB/kp"),
    DATABASE_PATH=os.getenv("DATABASE_PATH", "bot.db"),
    PORT=int(os.getenv("PORT", "8000")),
    WEBHOOK_URL=os.getenv("WEBHOOK_URL", ""),
)
