from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from pathlib import Path

from app.domain.file_locations import EXCEL_LOC
from app.models import PrefixPool, PrefixPoolType, ResourcePool, Role, Site
from app.utils import load_sheet


class SeedHandler:
    """
    Docstring for SeedHandler
    """

    WB_NAME = EXCEL_LOC.location
    
    def __init__(self, session, wb_name: str | Path = WB_NAME):
        
        self.session = session
        self.wb_name = wb_name
          
    def seed_sites(self) -> int:
        """
        Seed Site rows from the 'Site' sheet.
        Returns number of newly inserted sites.
        """
        df = load_sheet(sheet_name="Site", wb_name=self.wb_name)

        site_names = sorted({
            str(v).strip()
            for v in df["SiteName"].dropna()
            if str(v).strip()
        })

        inserted = 0

        for site_name in site_names:
            exists = (
                self.session.query(Site.id)
                .filter(Site.name == site_name)
                .first()
            )

            if exists:
                continue

            self.session.add(Site(name=site_name))
            inserted += 1

        if inserted:
            self.session.flush()

        return inserted
        
    
    def seed_roles(self) -> int:
        """
        Read Role rows from the 'Role' sheet.
        Returns number of newly inserted roles.
        """
        df = load_sheet(sheet_name="Role", wb_name=self.wb_name)

        role_names = sorted({
            str(v).strip()
            for v in df["RoleName"].dropna()
            if str(v).strip()
        })

        inserted = 0

        for role_name in role_names:
            if self.session.query(Role).filter_by(name=role_name).first():
                continue

            self.session.add(Role(name=role_name))
            inserted += 1

        if inserted:
            self.session.flush()

        return inserted
    
    def seed_resource_pools(self) -> int:
        """
        Read ResourcePoolName, StartRange and StopRange rows
        from the 'ResourcePools' sheet.
        If pool exists then insertion is skipped.

        Returns number of inserted pools.
        """
        df = load_sheet(sheet_name="ResourcePools", wb_name=self.wb_name)
        inserted = 0

        for _, row in df.iterrows():
            resource_pool_name = row["ResourcePoolName"]
            range_start = int(row["RangeStart"])
            range_end = int(row["RangeEnd"])

            exists = (
                self.session.query(ResourcePool)
                .filter_by(name=resource_pool_name)
                .first()
            )

            if exists:
                continue

            self.session.add(
                ResourcePool(
                    name=resource_pool_name,
                    range_start=range_start,
                    range_end=range_end,
                )
            )
            inserted += 1

        if inserted:
            self.session.flush()
        return inserted   
    
        
    def seed_prefix_pool_types(self) -> int:
        """
        Read Name row from the 'PrefixPoolTypes' sheet.
        If name exists then insertion is skipped.

        Returns number of inserted names.
        """
        df = load_sheet(sheet_name="PrefixPoolTypes", wb_name=self.wb_name)
        inserted = 0

        for _, row in df.iterrows():
            name = row["Name"]
            
            exists = (
                self.session.query(PrefixPoolType)
                .filter_by(name=name)
                .first()
            )

            if exists:
                continue

            self.session.add(
                PrefixPoolType(
                    name=name,                    
                )
            )
            inserted += 1

        if inserted:
            self.session.flush()
        return inserted

    def seed_prefix_pools(self) -> int:
        """
        Seed PrefixPool rows from the 'PrefixPools' sheet.
        Returns number of newly inserted pools.
        """
        df = load_sheet(sheet_name="PrefixPools", wb_name=self.wb_name)

        inserted = 0

        for _, row in df.iterrows():
            pool_name = str(row["PrefixPoolName"]).strip()
            type_name = str(row["PrefixPoolType"]).strip()
            prefix = str(row["Prefix"]).strip()

            if not pool_name or not type_name or not prefix:
                continue

            if self.session.query(PrefixPool).filter_by(name=pool_name).first():
                continue

            pool_type = self.session.query(PrefixPoolType).filter_by(name=type_name).first()
            if not pool_type:
                continue

            self.session.add(
                PrefixPool(
                    name=pool_name,
                    prefix=prefix,
                    type_id=pool_type.id,
                )
            )
            inserted += 1

        if inserted:
            self.session.flush()

        return inserted
    