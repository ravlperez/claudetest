from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Alembic Config object — provides access to values within alembic.ini.
config = context.config

# Set up Python logging from the ini file's [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- App wiring ----------------------------------------------------------
# Import the shared DeclarativeBase so Alembic can diff the schema against
# all registered models (populated in TASK 4+).
from src.app.database import Base, DATABASE_URL  # noqa: E402

# Override the URL in alembic.ini with whatever DATABASE_URL env var says.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata
# -------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (SQL script output mode)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
