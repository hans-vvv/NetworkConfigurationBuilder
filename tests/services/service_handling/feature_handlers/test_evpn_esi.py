from __future__ import annotations

from collections import defaultdict

import pytest
from sqlalchemy.orm import selectinload

from app.models import Device, Interface, ResourceAllocation, ResourcePool
from app.services.service_handling.feature_handlers.evpn_esi import (
    EVPN_ESIFeatureHandler,
)


@pytest.fixture()
def evpn_esi_ctx():
    return {
        "service_data": {
            "tenant": "lab",
            "service": "evpn_evi",
            "variant": "default",
            "selectors": {
                "devices": {
                    "evpn_esi": {
                        "match": {
                            "role": {"include": ["pe"]},
                        }
                    }
                }
            },
            "parameters": {
                "allocations": {
                    "evpn_esi": {
                        "pool": "evpn_esi_pool_demo",
                    }
                }
            },
        }
    }


@pytest.fixture()
def evpn_esi_ready_interfaces(session, seeded_inventory):
    def get_device(hostname: str) -> Device:
        dev = (
            session.query(Device)
            .filter(Device.hostname == hostname)
            .one_or_none()
        )
        assert dev is not None, f"Device {hostname} not found"
        return dev

    pe1 = get_device("pe1.Site11")
    pe2 = get_device("pe2.Site11")

    interfaces = []

    for dev in (pe1, pe2):
        iface = Interface(
            name="Bundle-Ether33",
            device=dev,
            intf_role="NNI",
            evpn_esi="needs esi",
            in_use=True,
        )
        session.add(iface)
        interfaces.append(iface)

    session.flush()
    return interfaces


def test_evpn_esi_assigns_esi_to_all_interfaces_marked_needs_esi(
    session,
    seeded_inventory,
    evpn_esi_ready_interfaces,
    dummy_service_builder,
    evpn_esi_ctx,
):
    handler = EVPN_ESIFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    handler.compute(svc_ctx=evpn_esi_ctx)

    refreshed = (
        session.query(Interface)
        .filter(Interface.id.in_([i.id for i in evpn_esi_ready_interfaces]))
        .all()
    )

    for iface in refreshed:
        assert iface.evpn_esi is not None
        assert iface.evpn_esi != ""
        assert iface.evpn_esi != "needs esi"


def test_evpn_esi_is_shared_per_site_and_interface_name_group(
    session,
    seeded_inventory,
    evpn_esi_ready_interfaces,
    dummy_service_builder,
    evpn_esi_ctx,
):
    handler = EVPN_ESIFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    handler.compute(svc_ctx=evpn_esi_ctx)

    ifaces = (
        session.query(Interface)
        .options(
            selectinload(Interface.device)
            .selectinload(Device.site)
        )
        .filter(Interface.id.in_([i.id for i in evpn_esi_ready_interfaces]))
        .all()
    )

    groups: dict[tuple[str, str], set[str]] = defaultdict(set)

    for iface in ifaces:
        site_name = iface.device.site.name
        groups[(site_name, iface.name)].add(iface.evpn_esi)

    for (_, _), esi_values in groups.items():
        assert len(esi_values) == 1


def test_evpn_esi_is_idempotent_no_new_allocations_on_rerun(
    session,
    seeded_inventory,
    evpn_esi_ready_interfaces,
    dummy_service_builder,
    evpn_esi_ctx,
):
    handler = EVPN_ESIFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    pool = (
        session.query(ResourcePool)
        .filter(ResourcePool.name == "evpn_esi_pool_demo")
        .one()
    )

    def allocation_count() -> int:
        return (
            session.query(ResourceAllocation)
            .filter(ResourceAllocation.pool_id == pool.id)
            .count()
        )

    before_first = allocation_count()
    handler.compute(svc_ctx=evpn_esi_ctx)
    session.flush()
    after_first = allocation_count()

    assert after_first > before_first

    snapshot = {
        i.id: i.evpn_esi
        for i in session.query(Interface).all()
    }

    before_second = allocation_count()
    handler.compute(svc_ctx=evpn_esi_ctx)
    session.flush()
    after_second = allocation_count()

    assert after_second == before_second

    snapshot_after = {
        i.id: i.evpn_esi
        for i in session.query(Interface).all()
    }

    assert snapshot_after == snapshot


def test_evpn_esi_returns_device_scoped_context(
    session,
    seeded_inventory,
    evpn_esi_ready_interfaces,
    dummy_service_builder,
    evpn_esi_ctx,
):
    handler = EVPN_ESIFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    result = handler.compute(svc_ctx=evpn_esi_ctx)

    assert "pe1.Site11" in result
    assert "pe2.Site11" in result

    for hostname in ("pe1.Site11", "pe2.Site11"):
        assert "evpn_esi" in result[hostname]
        assert "variant" in result[hostname]["evpn_esi"]
        assert "default" in result[hostname]["evpn_esi"]["variant"]

        interfaces = result[hostname]["evpn_esi"]["variant"]["default"]["interfaces"]
        assert isinstance(interfaces, list)
        assert interfaces[0]["if_name"] == "Bundle-Ether33"
        assert "esi" in interfaces[0]