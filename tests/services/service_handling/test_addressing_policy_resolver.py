from __future__ import annotations

import pytest

from app.models.dataclass_models import DeviceSelectorView, RoleView
from app.services.selectors.selector_engine import SelectorEngine
from app.services.service_handling.addressing_policy_resolver import (
    AddressingPolicyResolver,
)


@pytest.fixture()
def selector_engine(session):
    return SelectorEngine(session=session)


@pytest.fixture()
def resolver(selector_engine):
    resolver = AddressingPolicyResolver(selector_engine=selector_engine)
    resolver.install()
    return resolver


@pytest.fixture()
def make_device_view():
    def _make(
        *,
        hostname: str,
        role: str,
        tenant: str = "demo",
    ) -> DeviceSelectorView:
        return DeviceSelectorView(
            hostname=hostname,
            labels={"tenant": tenant},
            role=RoleView(name=role),
        )

    return _make


@pytest.mark.parametrize(
    "role,expected_pool",
    [
        ("core", "core_loopback0_pool_demo"),
        ("rr", "core_loopback0_pool_demo"),
        ("pe", "pe_loopback0_pool_demo"),
    ],
)
def test_resolve_loopback0_pool_by_role(
    resolver,
    make_device_view,
    role,
    expected_pool,
):
    view = make_device_view(
        hostname=f"{role}1.demo-001",
        role=role,
    )

    pool = resolver.resolve_loopback0_pool(view)
    assert pool == expected_pool


def test_resolve_loopback0_no_matching_policy_fails(
    resolver,
    make_device_view,
):
    view = make_device_view(
        hostname="core1.demo-001",
        role="core",
        tenant="unknown_tenant",
    )

    with pytest.raises(ValueError, match="No addressing policy matches device"):
        resolver.resolve_loopback0_pool(view)


def test_resolve_loopback0_missing_role_mapping_fails(
    resolver,
    make_device_view,
):
    view = make_device_view(
        hostname="aggregation1.demo-001",
        role="aggregation",
    )

    with pytest.raises(ValueError, match="No loopback0 pool defined for role"):
        resolver.resolve_loopback0_pool(view)


@pytest.mark.parametrize(
    "role_a,role_b,expected_pool",
    [
        ("core", "core", "p2p_pool_demo"),
        ("core", "pe", "p2p_pool_demo"),
        ("rr", "core", "p2p_pool_demo"),
        ("pe", "pe", "p2p_pool_demo"),
    ],
)
def test_resolve_p2p_pool_by_role_pair(
    resolver,
    make_device_view,
    role_a,
    role_b,
    expected_pool,
):
    dev_a = make_device_view(
        hostname=f"{role_a}1.demo-001",
        role=role_a,
    )
    dev_b = make_device_view(
        hostname=f"{role_b}2.demo-001",
        role=role_b,
    )

    pool = resolver.resolve_p2p_pool(dev_a, dev_b)
    assert pool == expected_pool


def test_resolve_p2p_no_matching_policy_fails(
    resolver,
    make_device_view,
):
    dev_a = make_device_view(
        hostname="core1.demo-001",
        role="core",
        tenant="demo",
    )
    dev_b = make_device_view(
        hostname="core2.other-001",
        role="core",
        tenant="other",
    )

    with pytest.raises(RuntimeError, match="No addressing policy matched devices"):
        resolver.resolve_p2p_pool(dev_a, dev_b)


def test_resolve_p2p_missing_role_pair_fails(
    resolver,
    make_device_view,
):
    dev_a = make_device_view(
        hostname="rr1.demo-001",
        role="rr",
    )
    dev_b = make_device_view(
        hostname="rr2.demo-001",
        role="rr",
    )

    with pytest.raises(RuntimeError, match="no p2p pool defined for role pair"):
        resolver.resolve_p2p_pool(dev_a, dev_b)


def test_install_requires_at_least_one_policy(
    selector_engine,
    tmp_path,
    monkeypatch,
):
    empty_dir = tmp_path / "addr_defs"
    empty_dir.mkdir()

    import app.services.service_handling.addressing_policy_resolver as resolver_mod

    monkeypatch.setattr(
        resolver_mod,
        "ADDRESSING_DEF_LOC",
        type("AddrLoc", (), {"location": str(empty_dir)})(),
    )

    resolver = AddressingPolicyResolver(selector_engine=selector_engine)

    with pytest.raises(ValueError, match="No addressing policies found"):
        resolver.install()