from dataclasses import dataclass


@dataclass(frozen=True)
class FileLocations:
    location: str
    

ADDRESSING_DEF_LOC = FileLocations(
    location="app/services/service_handling/addressing_definitions", 
)


SERVICES_DEF_LOC = FileLocations(
    location="app/services/services_definitions", 
)


EXCEL_LOC = FileLocations(
    location="app/demo.xlsx", 
)

PRODUCTION_DB_LOC = FileLocations(
    location="app.DB", 
)