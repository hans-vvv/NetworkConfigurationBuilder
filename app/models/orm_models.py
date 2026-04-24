from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ============================================================
# ROLE & SITE MODELS
# ============================================================
class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Site(Base):
    __tablename__ = "site"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="site",
        cascade="all, delete-orphan",
    )
    
    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("address.id", ondelete="SET NULL"),
        nullable=True
    )
    address: Mapped[Address | None] = relationship(
        "Address",
        back_populates="site"
    )
    
# ============================================================
# DEVICE & INTERFACE MODELS
# ============================================================
class Device(Base):
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hostname: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)    
    status: Mapped[str] = mapped_column(String(32), default="")    
    lag_name: Mapped[str] = mapped_column(String(32), default="")  # Ex: Bundle-Ether
    model_name: Mapped[str] = mapped_column(String(32), default="")
    # os_name: Mapped[str] = mapped_column(String(32), default="")
    labels: Mapped[dict[str, str]] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        nullable=False,
    )
    
    role_id: Mapped[int] = mapped_column(
        ForeignKey("role.id", name="fk_device_role_id"),
        nullable=True, index=True
    )
    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="devices",
    )
    
    site_id: Mapped[int] = mapped_column(
        ForeignKey("site.id", name="fk_device_site_id"),
        nullable=True, index=True
    )
    site: Mapped["Site"] = relationship(
        "Site",
        back_populates="devices",
    )
    interfaces: Mapped[list["Interface"]] = relationship(
        "Interface",
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="Interface.name",
    )   


class Interface(Base):
    __tablename__ = "interface"    

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(128))
    in_use: Mapped[bool] = mapped_column(Boolean, default=False)   
    intf_role: Mapped[str] = mapped_column(String(32), default="")  # NNI/CE/...
    evpn_esi: Mapped[str] = mapped_column(String(32), nullable=True, default=None)
    # connector: Mapped[str] = mapped_column(String(32), default="")

    __table_args__ = (
        Index(
            "ix_interface_needs_esi",
            "evpn_esi",
            sqlite_where=text("evpn_esi = 'needs esi'")
        ),        
        Index(
            "ix_interface_device_used_name",
            "device_id",
            "name",
            sqlite_where=text("in_use = 1"),
        ),        
        Index(
            "ix_interface_nni_used",
            "intf_role",
            sqlite_where=text("in_use = 1"),
        ),
    )    
    
    device_id: Mapped[int] = mapped_column(
        ForeignKey("device.id", name="fk_interface_device_id"),
        nullable=False, index=True
    )
    device: Mapped["Device"] = relationship(
        "Device",
        back_populates="interfaces",
    )

    ip_addresses: Mapped[list["IPAddress"]] = relationship(
        "IPAddress",
        back_populates="interface",
        cascade="all, delete-orphan",
    )

    cables_as_a: Mapped[list["Cable"]] = relationship(
        "Cable",
        back_populates="interface_a",
        foreign_keys="Cable.interface_a_id",
        cascade="all, delete-orphan",
    )

    cables_as_b: Mapped[list["Cable"]] = relationship(
        "Cable",
        back_populates="interface_b",
        foreign_keys="Cable.interface_b_id",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # LAG Support
    # ------------------------------------------------------------------

    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("interface.id"),
        nullable=True,
    )

    parent: Mapped[Optional["Interface"]] = relationship(
        back_populates="children",
        remote_side="Interface.id",
        uselist=False,
    )

    children: Mapped[list["Interface"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )

# ============================================================
# Cable class
# ============================================================
class Cable(Base):
    __tablename__ = "cable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    interface_a_id: Mapped[int] = mapped_column(
        ForeignKey("interface.id", name="fk_cable_interface_a"),
        nullable=False,
    )
    interface_a: Mapped["Interface"] = relationship(
        "Interface",
        foreign_keys=[interface_a_id],
        back_populates="cables_as_a",
    )

    interface_b_id: Mapped[int] = mapped_column(
        ForeignKey("interface.id", name="fk_cable_interface_b"),
        nullable=False,
    )
    interface_b: Mapped["Interface"] = relationship(
        "Interface",
        foreign_keys=[interface_b_id],
        back_populates="cables_as_b",
    )

    description: Mapped[Optional[str]] = mapped_column(String(128))
    in_use: Mapped[bool] = mapped_column(Boolean, default=False)


# ============================================================
# PREFIX POOL TYPES
# ============================================================
class PrefixPoolType(Base):
    __tablename__ = "prefix_pool_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    pools: Mapped[list["PrefixPool"]] = relationship(
        "PrefixPool",
        back_populates="pool_type",
        cascade="all, delete-orphan",
    )


# ============================================================
# PREFIX POOLS
# ============================================================
class PrefixPool(Base):
    __tablename__ = "prefix_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(128))

    type_id: Mapped[int] = mapped_column(
        ForeignKey("prefix_pool_type.id", name="fk_prefix_pool_type"),
        nullable=False,
    )
    pool_type: Mapped["PrefixPoolType"] = relationship(
        "PrefixPoolType",
        back_populates="pools",
    )

    prefixes: Mapped[list["Prefix"]] = relationship(
        "Prefix",
        back_populates="pool",
        cascade="all, delete-orphan",
    )

    ip_addresses: Mapped[list["IPAddress"]] = relationship(
        "IPAddress",
        back_populates="pool",
        cascade="all, delete-orphan",
    )


# ============================================================
# PREFIXES (/31, /30, ...)
# ============================================================
class Prefix(Base):
    __tablename__ = "prefix"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    in_use: Mapped[bool] = mapped_column(Boolean, default=False)
    # allocated: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)

    pool_id: Mapped[int] = mapped_column(
        ForeignKey("prefix_pool.id", name="fk_prefix_pool"),
        nullable=False,
    )
    pool: Mapped["PrefixPool"] = relationship(
        "PrefixPool",
        back_populates="prefixes",
    )

    ip_addresses: Mapped[list["IPAddress"]] = relationship(
        "IPAddress",
        back_populates="prefix",
        cascade="all, delete-orphan",
    )


# ============================================================
# IP ADDRESSES (/32 + /31 hosts)
# ============================================================
class IPAddress(Base):
    __tablename__ = "ip_address"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    in_use: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[Optional[str]] = mapped_column(String(32))  # loopback/link/mgmt

    pool_id: Mapped[int] = mapped_column(
        ForeignKey("prefix_pool.id", name="fk_ipaddress_pool"),
        nullable=False,
    )
    pool: Mapped["PrefixPool"] = relationship(
        "PrefixPool",
        back_populates="ip_addresses",
    )

    prefix_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prefix.id", name="fk_ipaddress_prefix"),
        nullable=True,
    )
    prefix: Mapped[Optional["Prefix"]] = relationship(
        "Prefix",
        back_populates="ip_addresses",
    )

    interface_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("interface.id", name="fk_ipaddress_interface"),
        nullable=True,
    )
    interface: Mapped[Optional["Interface"]] = relationship(
        "Interface",
        back_populates="ip_addresses",
    )

# ============================================================
# ADDRESSES
# ============================================================
class Address(Base):
    __tablename__ = "address"

    id = mapped_column(Integer, primary_key=True)
    street: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    site: Mapped["Site"] = relationship(
        "Site", back_populates="address", uselist=False
    )

# ============================================================
# Job class
# ============================================================
class Job(Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    # JSON blob containing full job description:
    # {
    #    "actions": [
    #        {"action": "add_device", "params": {...}},
    #        {"action": "add_cable", "params": {...}},
    #        ...
    #    ]
    # }

    actions_blob: Mapped[list[dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )    
    
    # job state: pending → executed (dry-run OK) → committed (applied to DB)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    results_blob: Mapped[dict | None] = mapped_column(JSON, default=dict)
    
    def __repr__(self):
        return f"<Job id={self.id} name={self.name} status={self.status}>"
    

# ============================================================
# User and UserRole classes
# ============================================================

class UserRole(Base):
    __tablename__ = "user_role"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="role",
        cascade="all, delete-orphan"
    )

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    role_id: Mapped[int] = mapped_column(
        ForeignKey("user_role.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped["UserRole"] = relationship(
        "UserRole",
        back_populates="users"
    )


class ServiceInstance(Base):
    __tablename__ = "service_instance"
    __table_args__ = (
        UniqueConstraint("svc_name", "tenant", "variant",
                         name="uq_service_instance_svc_tenant_variant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    svc_name: Mapped[str] = mapped_column(String, nullable=False)
    tenant: Mapped[str] = mapped_column(String, nullable=False) 
    variant: Mapped[str] = mapped_column(String, nullable=False)
    # type: Mapped[str] = mapped_column(String, nullable=False)
    computed: Mapped[dict] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Allocation(Base):
    """
    Represents a concrete, customer-specific service realization
    (e.g. evpn_l2vpn_customer_A).

    Guarantees that exactly one *complete* set of reservations exists
    when in_use == True.

    This table is used to enforce idempotency.
    """

    __tablename__ = "allocation"

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    # Example: "evpn_l2vpn_customer_A"

    # service_name: Mapped[str] = mapped_column(
    #     String(64),
    #     nullable=False,
    #     index=True,
    # )
    # Example: "evpn_l2vpn"

    # ------------------------------------------------------------------
    # Reservation latch
    # ------------------------------------------------------------------
    in_use: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    reservations: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # ------------------------------------------------------------------
    # Metadata / audit (non-semantic)
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
        

class ResourcePool(Base):
    __tablename__ = "resource_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # type: Mapped[str] = mapped_column(String, nullable=False)  # vlan, vxlan, rt, rd, sid

    range_start: Mapped[int] = mapped_column(Integer, nullable=False)
    range_end: Mapped[int] = mapped_column(Integer, nullable=False)

    allocation_strategy: Mapped[str] = mapped_column(
        String, default="sequential"
    )

    allocations: Mapped[list["ResourceAllocation"]] = relationship(
        back_populates="pool",
        cascade="all, delete-orphan"
    )


class ResourceAllocation(Base):
    __tablename__ = "resource_allocation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    pool_id: Mapped[int] = mapped_column(
        ForeignKey("resource_pool.id"), nullable=False
    )
    pool: Mapped["ResourcePool"] = relationship(
        back_populates="allocations"
    )
