from src.config import AppConfig

def check_env() -> None:
    cfg = AppConfig()
    missing = []
    if not cfg.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not cfg.serp_api_key:
        missing.append("SERPAPI_API_KEY")
    if missing:
        raise SystemExit(f"[ENV ERROR] Missing: {', '.join(missing)}")

    print("[OK] Env vars present.")
    print(f"[OK] OpenAI model: {cfg.openai_model}")
    print(f"[OK] SerpApi domain/gl/hl: {cfg.serp_google_domain}/{cfg.serp_gl}/{cfg.serp_hl}")