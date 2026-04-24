from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from typing import Any

import pandas as pd
from sqlalchemy.orm import aliased

from app.domain.file_locations import EXCEL_LOC
from app.models import Allocation, Cable, Device, Interface, IPAddress
from app.utils import db_session

WB_NAME = EXCEL_LOC.location

def write_report_tabs(session) -> None:
        """
        Build DB-derived reports and write them into the current workbook
        as tabs: report_devices and report_links.
        """
        df_devices = build_report_devices(session)
        df_links = build_report_links(session)

        with pd.ExcelWriter(
            WB_NAME,
            engine="openpyxl",
            mode="a",
            if_sheet_exists="replace",
        ) as writer:
            df_devices.to_excel(writer, sheet_name="report_devices", index=False)
            df_links.to_excel(writer, sheet_name="report_links", index=False) 


def build_report_devices(session) -> pd.DataFrame:
    """
    Build a normalized device report with tenant, hostname, system IP,
    management IP, and prefix SID.

    This function queries devices together with their system and management
    IP addresses and constructs a pandas DataFrame with the following columns:

    - tenant
    - hostname
    - system_ip
    - prefix_sid    

    Returns:
        pd.DataFrame with columns:
            - tenant
            - hostname
            - system_ip
            - prefix_sid
    """
    system_ip = aliased(IPAddress)
   
    q = (
        session.query(Device, system_ip.address)
        .join(Interface, Interface.device_id == Device.id)
        .outerjoin(
            system_ip,
            (system_ip.interface_id == Interface.id) & (system_ip.role == "system"),
        )       
    )

    by_host: dict[str, dict] = {}

    for dev, sys_ip in q.all():
        tenant = dev.labels.get("tenant")
        if tenant is None:
            continue

        rec = by_host.setdefault(
            dev.hostname,
            {
                "tenant": tenant,
                "system_ips": [],                
            },
        )

        if sys_ip:
            rec["system_ips"].append(sys_ip)
        
    sr_allocations = (
        session.query(Allocation)
        .filter(Allocation.name.startswith("sr_"))
        .all()
    )

    sid_by_hostname: dict[str, int] = {}
    for alloc in sr_allocations:
        reservations = alloc.reservations or {}
        for hostname, sid in reservations.items():
            sid_by_hostname[hostname] = sid

    rows = []
    for hostname in sorted(by_host):
        rec = by_host[hostname]

        system_ips = sorted(set(rec["system_ips"]))
       
        if len(system_ips) > 1:
            raise ValueError(f"Multiple system IPs for {hostname}: {system_ips}")
        if len(system_ips) == 0:
            raise ValueError(f"No system IP found for {hostname}")
                
        rows.append(
            {
                "tenant": rec["tenant"],
                "hostname": hostname,
                "system_ip": system_ips[0],                
                "prefix_sid": sid_by_hostname.get(hostname, pd.NA),
            }
        )

    return pd.DataFrame(rows)


def _single_link_ip(link_ips: list[str], *, context: str) -> str | Any:

    """
    Resolve a single unique IP address from a collection of link IPs.

    The function filters out falsy values (e.g., empty strings, None), deduplicates
    the remaining IPs, and returns a single IP if exactly one unique value exists.
    """
    ips = sorted({ip for ip in link_ips if ip})
    if len(ips) == 0:
        return pd.NA
    if len(ips) == 1:
        return ips[0]
    raise ValueError(f"Multiple link IPs for {context}: {ips}")


def build_report_links(session) -> pd.DataFrame:

    """
    Reports link info between nodes and IPs assigned on the links
    """

    IA = aliased(Interface)
    IB = aliased(Interface)
    DA = aliased(Device)
    DB = aliased(Device)

    # Cable -> physical interfaces -> devices
    cables = (
        session.query(Cable, IA, IB, DA, DB)
        .join(IA, Cable.interface_a_id == IA.id)
        .join(IB, Cable.interface_b_id == IB.id)
        .join(DA, IA.device_id == DA.id)
        .join(DB, IB.device_id == DB.id)
        .all()
    )

    # Preload link IPs per interface_id (role="link")
    link_ips_by_iface: dict[int, list[str]] = {}
    for iface_id, addr in (
        session.query(IPAddress.interface_id, IPAddress.address)
        .filter(IPAddress.role == "link")
        .all()
    ):
        if iface_id is None:
            continue
        link_ips_by_iface.setdefault(iface_id, []).append(addr)

    rows: list[dict] = []

    for _cable, ia, ib, da, db in cables:
        tenant = da.labels.get("tenant")
        if tenant is None:
            continue

        # physical endpoints
        devA, portA = da.hostname, ia.name
        devB, portB = db.hostname, ib.name

        # L3 interface for IP lookup (parent if LAG member)
        l3a = ia.parent if ia.parent_id else ia
        l3b = ib.parent if ib.parent_id else ib

        ipA = _single_link_ip(
            link_ips_by_iface.get(l3a.id, []),
            context=f"{devA}:{portA} (l3={l3a.name})",
        )
        ipB = _single_link_ip(
            link_ips_by_iface.get(l3b.id, []),
            context=f"{devB}:{portB} (l3={l3b.name})",
        )

        # canonicalize ordering to stabilize diffs
        if (devB, portB) < (devA, portA):
            devA, portA, ipA, devB, portB, ipB = devB, portB, ipB, devA, portA, ipA

        rows.append(
            {
                "tenant": tenant,
                "deviceA": devA,
                "portA": portA,
                "ipA": ipA,
                "deviceB": devB,
                "portB": portB,
                "ipB": ipB,
            }
        )
        # print(f"{devA}:{portA} -> {ipA} | {devB}:{portB} -> {ipB} (tenant={tenant})")

    df = pd.DataFrame(
        rows,
        columns=["tenant", "deviceA", "portA", "ipA", "deviceB", "portB", "ipB"],
    ).sort_values(
        ["tenant", "deviceA", "portA", "deviceB", "portB"],
        kind="mergesort",
    ).reset_index(drop=True)

    return df


if __name__ == "__main__":

    with db_session() as session:
        # build_report_devices(session)
        build_report_links(session)