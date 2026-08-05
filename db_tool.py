"""
Inspecciona o reconstruye el esquema local sin necesidad de psql.
Se conecta con el mismo SQLAlchemy/psycopg2 que ya usa la app.

    python db_tool.py inspect      # que columnas faltan o sobran
    python db_tool.py sql "ALTER TABLE users ADD COLUMN foo VARCHAR"
    python db_tool.py reset        # borra y recrea las tablas de los modelos
    python db_tool.py nuke         # borra el schema COMPLETO y lo recrea

Colocalo en la raiz del proyecto (junto a app/).
"""

import sys

from sqlalchemy import inspect, text

# Ajusta estos imports al layout real de tu proyecto.
from app.database import Base, engine  # noqa: E402
from app.models import health, job, plan_limits, user


def require_models() -> None:
    """Sin modelos registrados, todo lo demas miente en silencio."""
    if not Base.metadata.tables:
        print(
            "\nERROR: Base.metadata no tiene ninguna tabla.\n"
            "Los modelos no se estan importando, asi que inspect diria\n"
            "'alineado' y reset no haria nada.\n\n"
            "Importa los modulos explicitamente arriba, por ejemplo:\n"
            "    from app.models import user, job, plan_limits  # noqa: F401\n"
        )
        sys.exit(1)

    print(f"Modelos registrados: {len(Base.metadata.tables)} "
          f"-> {', '.join(sorted(Base.metadata.tables))}")


def require_local() -> None:
    url = engine.url
    if url.host not in ("localhost", "127.0.0.1", "postgres", "db"):
        print("\nCancelado: esta operacion solo se permite contra una base local.\n")
        sys.exit(1)


def show_url() -> None:
    url = engine.url
    print(f"\nConectado a: {url.host}:{url.port}/{url.database} (user {url.username})")
    if url.host not in ("localhost", "127.0.0.1", "postgres", "db"):
        print("  !! OJO: esto NO parece una base local.")
    print()


def inspect_schema() -> None:
    """Compara cada tabla del modelo contra la tabla real."""
    show_url()
    require_models()
    insp = inspect(engine)
    real_tables = set(insp.get_table_names())
    problems = 0

    for name, table in Base.metadata.tables.items():
        if name not in real_tables:
            print(f"[FALTA TABLA] {name}")
            problems += 1
            continue

        real_cols = {c["name"] for c in insp.get_columns(name)}
        model_cols = {c.name for c in table.columns}

        missing = model_cols - real_cols
        extra = real_cols - model_cols

        if missing or extra:
            print(f"\n{name}")
            for col in sorted(missing):
                column = table.columns[col]

                # El tipo generico de SQLAlchemy no siempre es SQL valido:
                # DateTime se imprime como DATETIME, que Postgres rechaza.
                # compile(dialect=...) da el tipo real del motor.
                ctype = column.type.compile(dialect=engine.dialect)

                nullable = "" if column.nullable else " NOT NULL"
                default = ""
                if column.server_default is not None:
                    default = f" DEFAULT {column.server_default.arg}"

                print(f"  [falta en la BD]  {col}  ({ctype})")
                print(
                    f"      ALTER TABLE {name} ADD COLUMN "
                    f"{col} {ctype}{default}{nullable};"
                )
                problems += 1
            for col in sorted(extra):
                print(f"  [sobra en la BD]  {col}")
                problems += 1

    print()
    if problems == 0:
        print("Esquema alineado con los modelos.")
    else:
        print(f"{problems} diferencia(s). Aplica los ALTER de arriba con:")
        print('  python db_tool.py sql "ALTER TABLE ..."')
    print()


def run_sql(statement: str) -> None:
    show_url()
    with engine.begin() as conn:
        conn.execute(text(statement))
    print(f"OK: {statement}\n")


def nuke() -> None:
    """
    Borra el schema public COMPLETO y lo recrea desde los modelos.

    A diferencia de reset, esto tambien elimina tablas que ya no existen
    en el codigo: no quedan residuos de versiones anteriores.
    """
    show_url()
    require_models()
    require_local()

    url = engine.url
    answer = input(
        f"Esto borra el schema 'public' ENTERO de '{url.database}'. Escribe NUKE: "
    )
    if answer.strip() != "NUKE":
        print("Cancelado.\n")
        return

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    Base.metadata.create_all(bind=engine)
    print("\nSchema recreado desde cero. Sin residuos.\n")


def reset() -> None:
    show_url()
    require_models()
    require_local()

    url = engine.url
    answer = input(f"Borrar las tablas de los modelos en '{url.database}'? escribe SI: ")
    if answer.strip() != "SI":
        print("Cancelado.\n")
        return

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("\nTablas recreadas desde los modelos actuales.\n")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "inspect":
        inspect_schema()
    elif command == "sql":
        if len(sys.argv) < 3:
            print("Falta la sentencia SQL.")
            sys.exit(1)
        run_sql(sys.argv[2])
    elif command == "reset":
        reset()
    elif command == "nuke":
        nuke()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
