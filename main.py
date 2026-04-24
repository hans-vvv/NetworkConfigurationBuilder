from app.domain.file_locations import EXCEL_LOC
from app.excel_data_handling.excel_data_handler import ExcelDataHandler
from app.excel_data_handling.reports import write_report_tabs
from app.excel_data_handling.seed_handler import SeedHandler
from app.excel_data_handling.snapshots import snapshot_failed, snapshot_latest
from app.printing.printer import Printer
from app.utils import db_session

# Creates roles, sites and resource pools in the dB
# Then reads app/demo.xlsx where topology is stored
# In this dir also the topology Demo.ppt is provided
# Returns sqlite app.DB  in the root dir which stores 
# computed data and topology

WB_NAME = EXCEL_LOC.location

try:
    with db_session() as session:
        seed = SeedHandler(session=session)
        edh = ExcelDataHandler(session=session)

        # edh.wipe_db() -> Enable when no dB is present in root dir and then disable
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
        edh.execute_job(job_name="do_all")
    
        snapshot_latest()
        write_report_tabs(session=session)

except Exception:        
    snapshot_failed()
    raise

# Device data is printed based on stored computed data in dB. 
# Note that this example does not produce correct syntax.
with db_session() as session:    
    printer = Printer(session=session)

    config = printer.render_device(hostname="pe1.Site9")    
    print(config)
