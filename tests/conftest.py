from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
WB_NAME = ROOT_DIR / "app" / "demo.xlsx"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

import pytest  # noqa: E402
from excel_data_handling.seed_handler import SeedHandler  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.engine import _set_sqlite_pragma  # noqa: E402, F401
from app.excel_data_handling.excel_data_handler import ExcelDataHandler  # noqa: E402
from app.services.selectors.selector_engine import SelectorEngine  # noqa: E402
from app.services.service_handling.resource_pool_allocator import (
    ResourcePoolAllocator,  # noqa: E402
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session: Session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def dummy_service_builder(session):
    return SimpleNamespace(
        selector_engine=SelectorEngine(session=session),
        rpa=ResourcePoolAllocator(session=session),
    )

@pytest.fixture()
def seeded_inventory(session):

    seeder = SeedHandler(session=session, wb_name=WB_NAME)
    edh = ExcelDataHandler(session=session, wb_name=WB_NAME)

    seeder.seed_sites()
    seeder.seed_roles()
    seeder.seed_resource_pools()
    seeder.seed_prefix_pool_types()
    seeder.seed_prefix_pools()

    edh.create_actions_blob_for_devices_loaded_from_excel()
    edh.create_actions_blob_for_cables_loaded_from_excel()
    edh.create_actions_blob_for_pe_devices_loaded_from_excel()            
    edh.create_actions_blob_for_pe_ring_cables_from_half_open_rings()
    edh.create_actions_blob_for_ces_loaded_from_excel()            
    edh.execute_job(job_name="test")

    session.flush()
    