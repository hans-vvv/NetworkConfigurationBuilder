from __future__ import annotations

import pytest

from app.models import Allocation, Device, Interface, ResourcePool
from app.repositories import get_all_devices
from app.services.service_handling.feature_handlers.evpn_l2vpn import (
    EVPN_L2VPNFeatureHandler,
)
from app.utils import require


@pytest.fixture()
def evpn_l2vpn_ctx():
    return {
        "service_data": {
            "service": "evpn_l2vpn",
            "tenant": "demo",
            "variant": "product_xyz",
            "selectors": {
                "devices": {
                    "evpn_l2vpn": {
                        "match": {
                            "labels": {"tenant": "demo"},
                            "role": {"include": ["pe"]},
                        }
                    }
                }
            },
            "parameters": {
                "l2vpns": [
                    {
                        "name": "customer_A",
                        "mtu": 1514,
                        "qos_policy_name": "BE",
                        "allocations": {
                            "vlan": {"poolname": "vlan_pool_demo"},
                            "rd": {"poolname": "rd_pool_demo"},
                        },
                    },
                    {
                        "name": "customer_B",
                        "mtu": 1514,
                        "qos_policy_name": "BE",
                        "allocations": {
                            "vlan": {"poolname": "vlan_pool_demo"},
                            "rd": {"poolname": "rd_pool_demo"},
                        },
                    },
                ]
            },
        }
    }


@pytest.fixture()
def evpn_l2vpn_vlan_pool(session, seeded_inventory):
    pool = session.query(ResourcePool).filter_by(name="vlan_pool_demo").one_or_none()
    if pool is None:
        pool = ResourcePool(
            name="vlan_pool_demo",
            range_start=1000,
            range_end=2000,
        )
        session.add(pool)
        session.flush()
    return pool


@pytest.fixture()
def evpn_l2vpn_rd_pool(session, seeded_inventory):
    pool = session.query(ResourcePool).filter_by(name="rd_pool_demo").one_or_none()
    if pool is None:
        pool = ResourcePool(
            name="rd_pool_demo",
            range_start=1000,
            range_end=2000,
        )
        session.add(pool)
        session.flush()
    return pool


@pytest.fixture()
def pe_devices(session, dummy_service_builder):
    all_devices = get_all_devices(session)
    selector = {
        "match": {
            "labels": {"tenant": "demo"},
            "role": {"include": ["pe"]},
        }
    }
    devices = dummy_service_builder.selector_engine.select(all_devices, selector)
    assert devices, "No PE demo devices found for EVPN L2VPN test"
    return devices


@pytest.fixture()
def evpn_l2vpn_ready_interfaces(session, pe_devices):
    interfaces = []

    for idx, dev in enumerate(pe_devices[:2], start=1):
        db_dev = session.query(Device).filter(Device.id == dev.id).one()
        iface = Interface(
            name=f"Bundle-Ether20{idx}",
            device=db_dev,
            intf_role="NNI",
            evpn_esi=f"0000.0000.0000.0000.0000.0000.0000.{idx}",
            in_use=True,
        )
        session.add(iface)
        interfaces.append(iface)

    session.flush()
    return interfaces


def test_evpn_l2vpn_returns_device_scoped_output(
    session,
    seeded_inventory,
    evpn_l2vpn_vlan_pool,
    evpn_l2vpn_rd_pool,
    evpn_l2vpn_ready_interfaces,
    evpn_l2vpn_ctx,
    dummy_service_builder,
):
    handler = EVPN_L2VPNFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    result = handler.compute(evpn_l2vpn_ctx)

    all_devices = get_all_devices(session)
    sel = evpn_l2vpn_ctx["service_data"]["selectors"]["devices"]["evpn_l2vpn"]
    expected = {
        d.hostname
        for d in dummy_service_builder.selector_engine.select(all_devices, sel)
    }

    assert set(result.keys()) == expected

    for hostname in expected:
        assert "evpn_l2vpn" in result[hostname]
        assert "variant" in result[hostname]["evpn_l2vpn"]
        assert isinstance(result[hostname]["evpn_l2vpn"]["variant"], dict)


def test_evpn_l2vpn_fails_if_underlay_not_ready(
    session,
    seeded_inventory,
    evpn_l2vpn_vlan_pool,
    evpn_l2vpn_rd_pool,
    pe_devices,
    evpn_l2vpn_ctx,
    dummy_service_builder,
):
    dev = session.query(Device).filter(Device.id == pe_devices[0].id).one()
    session.add(
        Interface(
            name="Bundle-Ether999",
            device=dev,
            intf_role="NNI",
            evpn_esi="needs esi",
            in_use=True,
        )
    )
    session.flush()

    handler = EVPN_L2VPNFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    with pytest.raises(RuntimeError, match="Underlay not ready"):
        handler.compute(evpn_l2vpn_ctx)


def test_evpn_l2vpn_is_idempotent(
    session,
    seeded_inventory,
    evpn_l2vpn_vlan_pool,
    evpn_l2vpn_rd_pool,
    evpn_l2vpn_ready_interfaces,
    evpn_l2vpn_ctx,
    dummy_service_builder,
):
    handler = EVPN_L2VPNFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    first = handler.compute(evpn_l2vpn_ctx)
    session.flush()
    second = handler.compute(evpn_l2vpn_ctx)

    assert first == second


def test_evpn_l2vpn_shares_rd_per_pair_label(
    session,
    seeded_inventory,
    evpn_l2vpn_vlan_pool,
    evpn_l2vpn_rd_pool,
    evpn_l2vpn_ready_interfaces,
    evpn_l2vpn_ctx,
    dummy_service_builder,
):
    handler = EVPN_L2VPNFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    result = handler.compute(evpn_l2vpn_ctx)

    by_pair_label = {}
    for intf in evpn_l2vpn_ready_interfaces:
        hostname = intf.device.hostname
        db_dev = require(
            session.query(Device).filter_by(hostname=hostname).one_or_none(),
            f"Device {hostname} missing",
        )
        pair_label = db_dev.labels.get("pair_label") or db_dev.hostname

        svc = result[hostname]["evpn_l2vpn"]["variant"]["product_xyz"]
        rd_values = tuple(item["rd"] for item in svc["l2vpns"])

        if pair_label in by_pair_label:
            assert by_pair_label[pair_label] == rd_values
        else:
            by_pair_label[pair_label] = rd_values


def test_evpn_l2vpn_persists_allocation_per_pair_label(
    session,
    seeded_inventory,
    evpn_l2vpn_vlan_pool,
    evpn_l2vpn_rd_pool,
    evpn_l2vpn_ready_interfaces,
    evpn_l2vpn_ctx,
    dummy_service_builder,
):
    handler = EVPN_L2VPNFeatureHandler(
        session=session,
        service_builder=dummy_service_builder,
    )

    handler.compute(evpn_l2vpn_ctx)
    session.flush()

    for intf in evpn_l2vpn_ready_interfaces:
        hostname = intf.device.hostname
        db_dev = require(
            session.query(Device).filter_by(hostname=hostname).one_or_none(),
            f"Device {hostname} missing",
        )
        pair_label = db_dev.labels.get("pair_label") or db_dev.hostname

        allocations = (
            session.query(Allocation)
            .filter(Allocation.reservations.contains(pair_label))
            .all()
        )

        assert allocations, f"No allocations found for pair_label={pair_label}"

        for allocation in allocations:
            assert allocation.in_use is True
            assert pair_label in allocation.reservations