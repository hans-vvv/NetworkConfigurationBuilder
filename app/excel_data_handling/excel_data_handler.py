from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import math
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.db import Base, engine
from app.domain.file_locations import EXCEL_LOC
from app.excel_data_handling.reports import write_report_tabs
from app.excel_data_handling.seed_handler import SeedHandler
from app.excel_data_handling.snapshots import snapshot_failed, snapshot_latest
from app.models import Job
from app.repositories import (
    get_job_by_name,
    get_role_by_name,
    get_site_by_name,
)
from app.services.job_handling.job_executor import JobExecutor
from app.utils import db_session, load_sheet, require
from app.validation.excel_input_checks import validate_excel_inputs


class ExcelDataHandler:
    """
    Orchestrates ingestion, validation, and transformation of Excel-based
    topology input into executable job actions.

    This class is responsible for:
    - Loading structured data from predefined Excel sheets.
    - Validating input data consistency and integrity.
    - Translating rows into normalized "action steps" (actions_blob)
      consumable by the JobExecutor.
    - Managing execution of those actions as a Job within the database.

    Core responsibilities:
    ----------------------
    1. Input validation:
        - Reads multiple sheets (Devices, Cables, DistDevices,
          HalfOpenRings, Site).
        - Delegates validation to `validate_excel_inputs`.
        - Fails fast if inconsistencies are detected.

    2. Action generation:
        - Converts Excel rows into structured action dictionaries.
        - Supports multiple domains:
            * Devices (PE, CE)
            * Cables (including derived ring topology)
            * PE pairs and CE attachments
        - Accumulates actions in `actions_blob`.

    3. Topology derivation:
        - Builds ring relationships from HalfOpenRings.
        - Infers inter-device cabling for Distribution PE chains.

    4. Job execution:
        - Persists actions as a Job entity (if not already present).
        - Executes actions via JobExecutor.
        - Clears internal state after execution.

    Attributes:
        session:
            Active database session used for lookups and persistence.

        wb_name:
            Path to the Excel workbook containing input data.

        actions_blob:
            In-memory list of action dictionaries representing the
            desired topology changes.

    Notes:
        - This class assumes strict schema and naming conventions
          in the Excel workbook.
        - Database entities (Site, Role, Job) must exist or be seeded
          prior to action generation.
        - The class is stateful: `actions_blob` is built incrementally
          and consumed during job execution.
    """

    WB_NAME = EXCEL_LOC.location
    
    def __init__(self, session, wb_name: str | Path = WB_NAME):
        
        self.session = session
        self.wb_name = wb_name
        self.actions_blob = []

    def validate_excel_input(self):
        """
        Load required Excel sheets and validate their contents.

        This method reads predefined sheets from the configured workbook,
        runs validation checks, and reports any detected issues.

        Workflow:
        - Load sheets: Devices, Cables, DistDevices, HalfOpenRings, Site.
        - Pass loaded DataFrames to the validation routine.
        - If validation errors are found:
            - Print up to the first 50 errors in a compact format.
            - Raise a ValueError summarizing the total number of errors.

        Raises:
            ValueError: If one or more validation errors are detected.
        """

        df_devices = load_sheet(sheet_name="Devices", wb_name=self.wb_name)
        df_cables = load_sheet(sheet_name="Cables", wb_name=self.wb_name)

        df_dist = load_sheet(sheet_name="DistDevices", wb_name=self.wb_name) 
        df_rings = load_sheet(sheet_name="HalfOpenRings", wb_name=self.wb_name)

        df_sites = load_sheet(sheet_name="Site", wb_name=self.wb_name)

        errors = validate_excel_inputs(
            df_devices=df_devices,
            df_dist=df_dist,
            df_cables=df_cables,
            df_half_open_rings=df_rings,
            df_sites=df_sites
        )

        if errors:
            # keep formatting minimal
            for e in errors[:50]:
                print(f"{e.sheet} r{e.row} c{e.column}: {e.message}")
            raise ValueError(f"Excel input validation failed ({len(errors)} errors)")

    def create_actions_blob_for_pe_devices_loaded_from_excel(self) -> None:

        """
        Reads "DistDevices" Excel tab and create actions step 
        for each row
        """

        df = load_sheet(sheet_name="DistDevices", wb_name=self.wb_name)

        ring_map = self._build_ring_map_from_half_open_rings()

        for row in df.to_dict("records"):
            device_name = row["DeviceName"]
            role_name = row["RoleName"]
            site_name = row["SiteName"]
            model_name = row["ModelName"]
            tenant = row["Tenant"]       

            if "," not in device_name:                
                self._create_actions_step_add_device(                    
                    site_name=site_name,
                    role_name=role_name,
                    hostname=device_name,
                    model_name=model_name,
                    tenant=tenant,
                    ring=ring_map[device_name],
                )
            else:
                dev_a, dev_b = [d.strip() for d in device_name.split(",")]
                self._create_actions_step_add_pe_pair(                   
                    site_name=site_name,
                    hostname_a=dev_a,
                    hostname_b=dev_b,
                    role_name=role_name,
                    model_name=model_name,
                    tenant=tenant,
                    ring=ring_map[dev_a],
                ) 
               
    def create_actions_blob_for_devices_loaded_from_excel(self) -> None:

        """
        Reads "Devices" Excel tab and create actions step 
        for each row
        """

        df = load_sheet(sheet_name="Devices", wb_name=self.wb_name)
        
        for row in df.to_dict("records"):

            self._create_actions_step_add_device(
                hostname = row["DeviceName"],
                role_name = row["DeviceRole"],
                site_name = row["Site"],
                model_name = row["Model"],
                tenant = row["Tenant"]
            )
    
    def create_actions_blob_for_ces_loaded_from_excel(self) -> None:

        """
        Reads "CEs" Excel tab and create actions step 
        for each row
        """
        
        df = load_sheet(sheet_name="CEs", wb_name=self.wb_name)
        
        for row in df.to_dict("records"):

            value: str = row.get("ConnectedPE", "")
            connected_pe = value.strip() if pd.notna(value) else None
            
            self._create_actions_step_attach_ce(
                ce_name = row["CEname"], 
                ce_role_name=row["CERole"],             
                site_name = row["SiteName"],
                model_name = row["ModelName"],                
                connected_pe=connected_pe 
            )
        
    def create_actions_blob_for_cables_loaded_from_excel(self) -> None:

        """
        Reads "Cables" Excel tab and create actions step 
        for each row
        """

        df = load_sheet(sheet_name="Cables", wb_name=self.wb_name)

        for row in df.to_dict("records"):
            self._create_actions_step_add_cable(
                dev_a_name=row["Device_a"],
                dev_b_name=row["Device_b"],
                iface_a_name=row["Iface_a"],
                iface_b_name=row["Iface_b"],
            )
    
    def create_actions_blob_for_pe_ring_cables_from_half_open_rings(self) -> None:
        """
        Emit add_cable actions for distribution PE half-open rings based on the
        HalfOpenRings sheet.

        Topology model
        --------------
        Each row represents one half-open ring between two core devices:

            coreX.<Termination_site_a>  ...dist-pe chain...  coreY.<Termination_site_b>

        The dist PE chain is defined by the remaining non-empty cells in the row,
        in sheet column order.

        Cell semantics
        --------------
        - A cell with one hostname, e.g. "pe1.Site9":
            entry = exit = "pe1.Site9"

        - A cell with two hostnames, e.g. "pe1.Site11,pe2.Site11":
            entry = "pe1.Site11"
            exit  = "pe2.Site11"

        The two hostnames in the same cell are assumed to already be cabled
        together internally, so this method must only emit the *external*
        inter-site cables:
            previous_exit -> next_entry

        Emitted cables
        --------------
        For each row, this method creates:
        - core_a -> entry(first site)
        - exit(site_i) -> entry(site_i+1)   for each adjacent pair
        - exit(last site) -> core_b

        Special case
        ------------
        If Termination_site_a == Termination_site_b, the far end is assumed to be
        a second core device on the same site, and agg_b becomes:
            core2.<Termination_site_b>
        instead of:
            core1.<Termination_site_b>
        """
        df = load_sheet(sheet_name="HalfOpenRings", wb_name=self.wb_name)

        for row in df.to_dict("records"):
            site_a = str(row.get("Termination_site_a") or "").strip()
            site_b = str(row.get("Termination_site_b") or "").strip()

            if not site_a or not site_b:
                continue

            core_a = f"core1.{site_a}"
            core_b = f"core1.{site_b}"

            if site_a == site_b:                
                core_b = f"core2.{site_b}"

            chain: list[tuple[str, str]] = []

            for col, val in row.items():
                if col in ("Termination_site_a", "Termination_site_b") or pd.isna(val):
                    continue

                cell = str(val).strip()
                if not cell:
                    continue

                parts = [p.strip() for p in cell.split(",") if p.strip()]

                if len(parts) == 1:
                    entry = exit_ = parts[0]
                else:
                    entry = parts[0]
                    exit_ = parts[1]

                chain.append((entry, exit_))

            if not chain:
                continue

            self._create_actions_step_add_cable(
                dev_a_name=core_a,
                dev_b_name=chain[0][0],
            )

            for i in range(len(chain) - 1):
                self._create_actions_step_add_cable(
                    dev_a_name=chain[i][1],
                    dev_b_name=chain[i + 1][0],
                )

            self._create_actions_step_add_cable(
                dev_a_name=chain[-1][1],
                dev_b_name=core_b,
            )   
    
    def _create_actions_step_add_device(
            self,
            *,           
            site_name: str,
            role_name: str,
            hostname: str,
            model_name: str,
            tenant: str,
            ring: str | None = None,
    ) -> dict:
        
        """
        Creates actions step for Job Handlers
        """

        site = require(get_site_by_name(self.session, site_name),
                       f"No dB record exists for {site_name}"
                       )
        role = require(get_role_by_name(self.session, role_name),
                       f"No dB record exists for {role_name}"
                       )

        actions_step = {
            "action": "add_device",
                "params": {
                    "hostname": hostname,
                    "role": role.name,
                    "site": site.name,
                    "model_name": model_name,
                    "tenant": tenant,
                    "ring": ring
                }
        }
        self.actions_blob.append(actions_step)
        return actions_step
    
    def _create_actions_step_attach_ce(
            self,
            *,           
            ce_name: str,
            ce_role_name: str,
            site_name: str,
            model_name: str,
            connected_pe: str | None = None          
    ) -> dict:
        
        """
        Creates actions step for Job Handlers
        """

        site = require(get_site_by_name(self.session, site_name),
                       f"No dB record exists for {site_name}"
        )
        ce_role = require(get_role_by_name(self.session, ce_role_name),
                       f"No dB record exists for {ce_role_name}"
        )

        actions_step = {
            "action": "attach_ce",
                "params": {
                    "ce_name": ce_name,
                    "ce_role_name": ce_role.name,
                    "site_name": site.name,
                    "ce_model_name": model_name,                    
                    "connected_pe": connected_pe,                   
                }
        }
        self.actions_blob.append(actions_step)
        return actions_step
    
    def _create_actions_step_add_pe_pair(
        self,
        *,
        site_name: str,
        hostname_a: str,
        hostname_b: str,
        role_name: str,
        model_name: str,
        tenant: str,
        ring: str | None = None,
) -> dict:        
        """
        Creates actions step for Job Handlers
        """
        site = require(get_site_by_name(self.session, site_name), 
               f"No dB record exists for {site_name}"
        )
        role = require(get_role_by_name(self.session, role_name),
               f"No dB record exists for {role_name}"
        )

        params = {
            "role": role.name,
            "site": site.name,
            "hostname_a": hostname_a,
            "hostname_b": hostname_b,
            "model_name": model_name,
            "tenant": tenant,
            "ring": ring,
        }
        
        actions_step = {"action": "add_pe_pair", "params": params}
        self.actions_blob.append(actions_step)
        return actions_step

    def _create_actions_step_add_cable(
            self,
            *,
            dev_a_name: str,
            dev_b_name: str,            
            iface_a_name=None,
            iface_b_name=None,
    ) -> dict:
        """
        Creates actions step for Job Handlers
        """

        actions_step = {
            "action": "add_cable",            
            "params": {
                "device_a_name": self._clean_scalar(dev_a_name),
                "device_b_name": self._clean_scalar(dev_b_name),
                "iface_a_name": self._clean_scalar(iface_a_name),
                "iface_b_name": self._clean_scalar(iface_b_name),                
            }
        }

        self.actions_blob.append(actions_step)
        return actions_step

    def _build_ring_map_from_half_open_rings(self) -> dict[str, str]:
        """
        Build a mapping of distribution PE device hostname -> ring identifier
        based on the HalfOpenRings Excel sheet tab.

        Each row in the sheet represents one half-open ring:
        - 'Termination_site_a' and 'Termination_site_b' define the two
            aggregation sites forming the ring endpoints.
        - All other non-empty cells in the row contain distribution PE device
            hostnames (either single hostname or comma-separated pair).

        The ring identifier is constructed as:
            "<siteA>:<siteB>"
        where the two site names are sorted lexicographically to ensure
        a stable and deterministic key.

        Returns:
            dict[str, str]:
                Mapping of device hostname -> ring string.

        Example:
            If a row contains:
                Termination_site_a = "Site3"
                Termination_site_b = "Site5"
                site_name_3 = "pe1.Site11, pe2.Site11" 
"

            The resulting mapping will include:
                {
                    "pe1.Site11": "Site3:Site5",
                    "pe2.Site11": "Site3:Site5",
                }
        """
        df = load_sheet(sheet_name="HalfOpenRings", wb_name=self.wb_name)
        ring_map: dict[str, str] = {}

        for row in df.to_dict("records"):
            # Read termination sites directly
            site_a = str(row.get("Termination_site_a") or "")
            site_b = str(row.get("Termination_site_b") or "")

            if not site_a or not site_b:
                continue

            ring = ":".join(sorted([site_a, site_b]))
            
            # Collect all device cells in the row
            for col, val in row.items():
                if col in ("Termination_site_a", "Termination_site_b"):
                    continue
                if pd.isna(val):
                    continue

                cell = str(val).strip()
                if not cell:
                    continue

                # Cell may contain "pe1.Site11, pe2.Site11"
                for hostname in [x.strip() for x in cell.split(",") if x.strip()]:
                    ring_map[hostname] = ring   

        return ring_map   
 

    def _clean_scalar(self, x: Any) -> Optional[Any]:
        """
        Normalize a scalar value by converting empty or invalid inputs to None.

        Rules:
        - None is returned as None.
        - NaN (float) is treated as missing and converted to None.
        - Strings are stripped of leading/trailing whitespace:
            - If the result is an empty string, return None.
            - Otherwise, return the cleaned string.
        - All other values are returned unchanged.

        Args:
            x: The input scalar value to clean.

        Returns:
            The cleaned value, or None if the input is considered empty or invalid.
        """
        if x is None:
            return None
        if isinstance(x, float) and math.isnan(x):
            return None
        if isinstance(x, str):
            x = x.strip()
            return x or None
        return x
    
    @staticmethod
    def wipe_db():

        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    
    def execute_job(self, *, job_name: str) -> bool:

        job = get_job_by_name(self.session, job_name)
        if job is None:
            job = Job(name=job_name, actions_blob=self.actions_blob)
            self.session.add(job)
            self.session.flush()

        executor = JobExecutor(session=self.session)
        topology_changed = executor.execute(job)
        self.actions_blob.clear()

        return topology_changed
    

if __name__ == "__main__":
    
    try:
        with db_session() as session:
            seed = SeedHandler(session=session)
            edh = ExcelDataHandler(session=session)

            edh.wipe_db()
            edh.validate_excel_input()            
            seed.seed_roles()
            seed.seed_sites()
            seed.seed_prefix_pool_types()
            seed.seed_prefix_pools()
            seed.seed_resource_pools()

            edh.create_actions_blob_for_devices_loaded_from_excel()
            edh.create_actions_blob_for_cables_loaded_from_excel()
            edh.create_actions_blob_for_pe_devices_loaded_from_excel()            
            edh.create_actions_blob_for_pe_ring_cables_from_half_open_rings()
            edh.create_actions_blob_for_ces_loaded_from_excel()            
            topology_changed = edh.execute_job(job_name="do_all")

        topology_changed = True   
        if topology_changed:
            snapshot_latest()
            write_report_tabs(session=session)

    except Exception:        
        snapshot_failed()
        raise
        