import unittest

from sqlalchemy import create_engine, text

from app.migrate import upgrade_schema


class MigrationsTest(unittest.TestCase):
    def test_upgrade_existing_unversioned_database_preserves_flows_and_deployments(self):
        database = create_engine("sqlite://")
        self.addCleanup(database.dispose)
        upgrade_schema(database, "0001")
        with database.begin() as db:
            db.execute(text(
                "INSERT INTO flows (id, name, current_version, definition, status, created_at) "
                "VALUES ('legacy', 'Legacy flow', 1, '{}', 'PUBLISHED', CURRENT_TIMESTAMP)"
            ))
            db.execute(text(
                "INSERT INTO deployments (id, flow_id, flow_version, target_class, status, created_at) "
                "VALUES ('legacy-deployment', 'legacy', 1, 'legacy-class', 'PENDING', CURRENT_TIMESTAMP)"
            ))
            db.execute(text("DROP TABLE alembic_version"))

        upgrade_schema(database)
        upgrade_schema(database)
        with database.connect() as db:
            self.assertEqual(db.scalar(text("SELECT version_num FROM alembic_version")), "0003")
            self.assertEqual(db.execute(text("SELECT id, status FROM flows")).one(), ("legacy", "PUBLISHED"))
            self.assertEqual(db.execute(text("SELECT id, agent_id, status FROM deployments")).one(),
                             ("legacy-deployment", None, "PENDING"))
            self.assertEqual(db.scalar(text("SELECT count(*) FROM flow_artifacts")), 0)
            self.assertEqual(db.execute(text("SELECT flow_id, version, name FROM flow_revisions")).one(),
                             ("legacy", 1, "Legacy flow"))
