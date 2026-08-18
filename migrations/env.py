"""
Configuracion de Alembic para data-link-api.

Reemplaza el migrations/env.py que genera `alembic init`.

Dos cosas que hace distinto al de fabrica:
  1. La URL sale de Settings, no de alembic.ini — asi local y prod usan la
     misma configuracion que la app y no hay una URL duplicada que se
     desincronice.
  2. Importa TODOS los modelos. Sin eso Base.metadata sale incompleta y el
     autogenerate propone BORRAR las tablas que no ve. Es el mismo tropiezo
     que hubo con db_tool.py y con el worker.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# --- Modelos: importar todos, aunque el linter los marque sin usar ---------
from app.database import Base
from app.models import job, plan_limits, user  # noqa: F401
from app.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

# Ajusta el nombre del campo si en tu Settings se llama distinto
# (database_url, db_url, postgres_url...).
config.set_main_option("sqlalchemy.url", str(settings.database_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse. Util para revisar que haria un upgrade."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # compare_type detecta cambios de tipo (VARCHAR(20) -> VARCHAR(50)),
            # que por defecto Alembic ignora.
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
