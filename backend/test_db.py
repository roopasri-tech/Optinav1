
from app.config.settings import settings
from sqlalchemy import create_engine, text

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"sslmode": "require"}
)

try:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )

        tables = [row[0] for row in result]

        if tables:
            print("Existing tables:")
            for table in tables:
                print("-", table)
        else:
            print("No tables found in the public schema.")

        result = connection.execute(
            text("SELECT to_regclass('public.alembic_version')")
        )
        print("Alembic version table:", result.scalar())
finally:
    engine.dispose()
