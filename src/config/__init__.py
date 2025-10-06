from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class AppConfig(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_org: str = os.getenv("OPENAI_ORG", "")
    openai_project: str = os.getenv("OPENAI_PROJECT", "")

    serp_api_key: str = os.getenv("SERPAPI_API_KEY", "")
    serp_google_domain: str = os.getenv("SERPAPI_GOOGLE_DOMAIN", "google.co.in")
    serp_gl: str = os.getenv("SERPAPI_GL", "in")
    serp_hl: str = os.getenv("SERPAPI_HL", "en")

    def validate_keys(self) -> None:
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.serp_api_key:
            missing.append("SERPAPI_API_KEY")
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")