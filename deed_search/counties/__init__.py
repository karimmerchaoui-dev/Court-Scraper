import importlib

"""counties = [
    "ocean_county",
    "broward_county",
    "duval_county",
    "polk_county",
    "brevard_county",
    "volusia_county",
    "osceola_county",
    "essex_county",
    "sussex_county",
    "atlantic_county",
    "bergen_county",
    "cumberland_county",
    "burlington_county",
    "union_county",
    "monmouth_county",
    "camden_county",
    "middlesex_county",
    "mercer_county",
    "cape_may_county",
    "hudson_county",
    "passaic_county",
    "morris_county",
]"""
counties = [
    "ocean_county",
    "volusia_county",
    "osceola_county",
    "essex_county",
    "sussex_county",
    "atlantic_county",
    "bergen_county",
    "burlington_county",
    "camden_county",
    "middlesex_county",
    "mercer_county",
    "cape_may_county",
    "gloucester_county",
    "union_county",
    "salem_county",
    "morris_county",
    "hudson_county",
    "brevard_county",
]

for county in counties:
    importlib.import_module(f"deed_search.counties.{county}")