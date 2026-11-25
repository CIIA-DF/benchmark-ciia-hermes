import os

import uvicorn


def main():
    if os.getenv("SEED_SYNTHETIC") == "1":
        from scripts.demo import seed

        seed()
    uvicorn.run(
        "services.backend.app:create_app", factory=True, host="0.0.0.0", port=8000, access_log=False
    )


if __name__ == "__main__":
    main()
