from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import ipaddress

from sqlalchemy.orm import Session

# from app.db import Base, engine
from app.models import (
    Allocation,
    IPAddress,
    Prefix,
    PrefixPool,
    ResourceAllocation,
    ResourcePool,
)
from app.repositories import (
    get_ips_for_pool,
    get_prefixes_by_pool,
)
from app.utils import require


class ResourcePoolAllocator:

    """
    Allocates IP prefixes, IP addresses, and numeric resources from
    ResourcePool and PrefixPool objects.

    This allocator supports two usage patterns:

    1. Direct allocation from a provided pool (e.g. loopbacks, p2p links),
       where no YAML input is involved.

    2. Allocation driven by validated service YAML specifications,
       where allocation policies and pool names are derived from
       service definition files.

    Idempotency rules:    
    - Per service-instance allocations are idempotent and persisted
      via Allocation records.

    This class assumes that all YAML files have been validated upfront by 
    the caller. Missing keys or malformed structures are treated as 
    programmer errors.
    """
    def __init__(self, session: Session):
        self.session = session
        self._cache = {}

    # ----------------------------------------------------------------------
    # /32 ALLOCATOR
    # ----------------------------------------------------------------------
    def allocate_loopback(
        self,
        pool: PrefixPool,
        role: str = "loopback",
    ) -> IPAddress:
        """
        Allocate the next free /32 IP address inside a PrefixPool.

        Assumes the pool.prefix is a parent block (e.g., 10.10.0.0/16).        

        Raises
        ------
        RuntimeError
            If no /32 address is available.
        """
        network = ipaddress.ip_network(pool.prefix)
        existing_ips = get_ips_for_pool(self.session, pool)

        used_hosts = {
            ipaddress.ip_address(ip.address.split("/")[0])
            for ip in existing_ips
        }

        for host in network.hosts():
            if host not in used_hosts:
                ip_obj = IPAddress(
                    address=f"{host}/32",
                    pool_id=pool.id,
                    prefix_id=None,
                    role=role,
                    in_use=False,
                )
                self.session.add(ip_obj)
                self.session.flush()
                return ip_obj

        raise RuntimeError(f"No free /32 addresses left in pool {pool.name}")

    # ----------------------------------------------------------------------
    # /31 ALLOCATOR
    # ----------------------------------------------------------------------
    def allocate_p2p_prefix(self, pool: PrefixPool) -> Prefix:
        """
        Allocate a free /31 prefix from the given pool.       

        Raises
        ------
        RuntimeError
            If no /31 prefix is available.
        """
        parent_network = ipaddress.ip_network(pool.prefix)
        used_prefixes = {
            ipaddress.ip_network(p.prefix)
            for p in get_prefixes_by_pool(self.session, pool)
        }

        for candidate in parent_network.subnets(new_prefix=31):
            if candidate not in used_prefixes:
                prefix = Prefix(
                    prefix=str(candidate),
                    pool_id=pool.id,
                    in_use=True,
                )
                self.session.add(prefix)
                self.session.flush()
                return prefix

        raise RuntimeError(f"No free /31 prefixes left in pool {pool.name}")

    # ----------------------------------------------------------------------
    # HOST IP ALLOCATION FOR /31
    # ----------------------------------------------------------------------
    def allocate_ips_for_p2p(
        self,
        prefix: Prefix,
        role: str = "link",
    ) -> list[IPAddress]:
        """
        Create two IP addresses inside a /31 Prefix.       

        Raises
        ------
        RuntimeError
            If prefix is not a /31 block.
        """
        network = ipaddress.ip_network(prefix.prefix)
        hosts = list(network.hosts())

        if network.prefixlen != 31:
            raise RuntimeError(f"Prefix {prefix.prefix} is not a valid /31 network")

        results: list[IPAddress] = []
        for host in hosts:
            ip_obj = IPAddress(
                address=f"{host}/31",
                pool_id=prefix.pool_id,
                prefix_id=prefix.id,
                role=role,
                in_use=False,
            )
            self.session.add(ip_obj)
            results.append(ip_obj)

        self.session.flush()
        return results

    # ----------------------------------------------------------------------
    # CONVENIENCE: allocate both prefix and IP pairs
    # ----------------------------------------------------------------------
    def allocate_full_p2p(self, pool: PrefixPool) -> tuple[Prefix, list[IPAddress]]:
        """
        Allocate both the /31 prefix AND its two IP addresses.
        """
        prefix = self.allocate_p2p_prefix(pool)
        ips = self.allocate_ips_for_p2p(prefix)
        return prefix, ips 

    
    def allocate_delegated_prefix_per_service_instance(
        self,
        *,
        allocation_name: str,
        pool: PrefixPool,
        prefixlen: int,       
    ) -> dict[str, str]:
        """
        Idempotency is guarenteed based on service_instance_name
        Reserves prefix from delegated pool.
        """
        allocation = (
            self.session.query(Allocation)
            .filter_by(name=allocation_name)
            .one_or_none()
        )

        if allocation and allocation.in_use:
            return allocation.reservations

        if not allocation:
            allocation = Allocation(
                name=allocation_name,
                in_use=False,
                reservations={},
            )
            self.session.add(allocation)
            self.session.flush()

        # allocate new delegated prefix
        parent = ipaddress.ip_network(pool.prefix)
        used = {
            ipaddress.ip_network(p.prefix)
            for p in get_prefixes_by_pool(self.session, pool)
        }

        for candidate in parent.subnets(new_prefix=prefixlen):
            if candidate not in used:
                delegated = Prefix(
                    prefix=str(candidate),
                    pool_id=pool.id,
                    in_use=True,
                )
                self.session.add(delegated)
                self.session.flush()
                break
        else:
            raise RuntimeError(f"No free /{prefixlen} in pool {pool.name}")

        allocation.reservations = {"prefix": delegated.prefix}
        allocation.in_use = True
        self.session.flush()

        return allocation.reservations

    
    # ----------------------------------------------------------------------
    # Resource pools
    # ----------------------------------------------------------------------
    def allocate_per_service_instance(
        self,
        *, 
        allocation_name: str,
        allocations: dict[str, str]

    ) -> dict[str, int]:
        """
        Idempotency can be enforced by unique allocation name.        

        example of allocations dict:
            {
                "vlan": "evpn_vlan_pool",
                "rd": "evpn_rd_pool",
                "rt": "evpn_rt_pool",
            }
        YAML files are required to be validated upfront.       
        """

        reservations: dict[str, int] = {}   

        # Service-bound per allocation_name (idempotent)  
        allocation = (
            self.session.query(Allocation)
            .filter_by(name=allocation_name)
            .one_or_none()
        )

        if allocation and allocation.in_use:
            return allocation.reservations        
        
        if not allocation:           
            allocation = Allocation(
                name=allocation_name,                
                in_use=False,
                reservations={},
            )
            self.session.add(allocation)
            self.session.flush()        

        for alloc, pool_name in allocations.items():
            value = self._make_reservation(pool_name=pool_name)
            reservations[alloc] = value 

        allocation.reservations = reservations
        allocation.in_use = True
        self.session.flush()

        return reservations    
    

    def _make_reservation(self, pool_name):
        """
        Makes reservation in specified pool_name of Type ResourcePool
        The caller is resposible of idempotency
        """

        pool = (
            self.session.query(ResourcePool)
            .filter_by(name=pool_name)
            .one_or_none()
        )
        pool = require(pool, f"ResourcePool '{pool_name}' not found in dB")

        used = {alloc.value for alloc in pool.allocations}

        for candidate in range(pool.range_start, pool.range_end + 1):
            if candidate not in used:
                value = candidate
                break
        else:
            raise RuntimeError(
                f"Pool '{pool_name}' exhausted "                
            )

        alloc = ResourceAllocation(
            pool=pool,                
            value=value,
        )
        self.session.add(alloc)
        self.session.flush()
    
        return value
