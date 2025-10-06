import argparse
from src.utils.doctor import check_env

def main():
    parser = argparse.ArgumentParser(description="SY PDP SEO/AEO content generator")
    parser.add_argument("--doctor", action="store_true", help="Validate environment and config.")
    args = parser.parse_args()

    if args.doctor:
        check_env()
        print("[READY] You can proceed to ingestion and generation steps next.")

if __name__ == "__main__":
    main()