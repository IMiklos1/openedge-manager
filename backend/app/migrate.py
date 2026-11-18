from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from .db import engine


def upgrade_schema(database: Engine = engine, revision: str = "head"):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    with database.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(772431600)")
        elif connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


if __name__ == "__main__":
    upgrade_schema()
