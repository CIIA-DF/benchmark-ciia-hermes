from app.config import Settings
from app.db.session import IndexConfigurationError, create_database_engine, initialize_database
from sqlalchemy.exc import SQLAlchemyError


def main() -> None:
    try:
        settings = Settings()
        engine = create_database_engine(settings)
        try:
            initialize_database(engine, settings)
        finally:
            engine.dispose()
    except IndexConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    except (SQLAlchemyError, ValueError):
        raise SystemExit(
            "Confira a configuração, o acesso ao PostgreSQL e a extensão pgvector."
        ) from None
    print("Banco RAG inicializado.")


if __name__ == "__main__":
    main()
