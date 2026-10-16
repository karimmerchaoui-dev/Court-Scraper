"""
County configuration — COUNTY_CONFIGS, STEP_VERIFIERS, DOWNLOAD_FUNCTIONS,
VPN_RESET_COUNTIES, and related lookup helpers.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# ── County navigation / search / trigger imports ─────────────────────────────
from counties.florida.brevard_helpers import (
    navigate_to_search_brevard,
    navigate_to_url_brevard,
    search_case_number_brevard,
    trigger_download_brevard,
)
from counties.florida.broward_helpers import (
    navigate_to_files_table_bw,
    navigate_to_search_bw,
    navigate_to_url_bw,
    search_case_number_bw,
    trigger_download_bw,
)
from counties.florida.duval_helpers import (
    navigate_to_files_table_dv,
    search_case_dv,
    trigger_download_dv,
)
from counties.florida.lee_helpers import (
    navigate_to_files_table_lee,
    navigate_to_search_lee,
    navigate_to_url_lee,
    search_case_number_lee,
    trigger_download_lee,
)
from counties.florida.manatee import (
    navigate_to_files_table_manatee,
    navigate_to_url_manatee,
    trigger_download_manatee,
)
from counties.florida.miami_helpers import (
    navigate_to_files_table_md,
    navigate_to_search_md,
    navigate_to_url_md,
    search_case_number_md,
    trigger_download_miami,
)
from counties.florida.orange_helpers import (
    navigate_to_files_table_oc,
    navigate_to_search_oc,
    navigate_to_url_oc,
    search_case_number_oc,
    trigger_download_oc,
)
from counties.florida.osceola_helpers import (
    navigate_to_files_table_osceola,
    navigate_to_search_osceola,
    navigate_to_url_osceola,
    search_case_number_osceola,
    trigger_download_osceola,
)
from counties.florida.palm_beach import (
    enter_docket_number_pb,
    navigate_to_files_pb,
    navigate_to_search_pb,
    navigate_to_url_pb,
    show_docket_pb,
    show_parties_pb,
    trigger_download_pb,
)
from counties.florida.polk_helpers import (
    navigate_to_files_table_polk,
    navigate_to_search_polk,
    navigate_to_url_polk,
    search_case_number_polk,
    show_parties_polk,
    trigger_download_polk,
)
from counties.florida.sarasota import (
    navigate_to_files_table_sarasota,
    navigate_to_search_sarasota,
    navigate_to_url_sarasota,
    search_case_number_sarasota,
    trigger_download_sarasota,
)
from counties.florida.seminole_helpers import (
    navigate_to_files_table_seminole,
    navigate_to_url_seminole,
    search_case_number_seminole,
    trigger_download_seminole,
)
from counties.florida.vs_helpers import (
    navigate_to_files_table_vs,
    navigate_to_search_vs,
    navigate_to_url_vs,
    search_case_number_vs,
    show_dockets_vs,
    show_parties_vs,
    trigger_download_vs,
)

# ── Browser helpers for STEP_VERIFIERS ────────────────────────────────────────
from browser.browser_helpers import element_exists_id, element_exists_xpath

# ── Config constants ──────────────────────────────────────────────────────────
COUNTY_DISPLAY_NAMES = {
    'jersey': 'New Jersey', 'nj': 'New Jersey',
    'miami': 'Miami Dade', 'orange': 'Orange County',
    'broward': 'Broward', 'lee': 'Lee',
    'palm': 'Palm Beach', 'duval': 'Duval',
    'pinn': 'Pinellas', 'volusia': 'Volusia',
    'brevard': 'Brevard', 'polk': 'Polk',
    'seminole': 'Seminole',
}

# ══════════════════════════════════════════════════════════════════════════════
# COUNTY CONFIGS
# ══════════════════════════════════════════════════════════════════════════════

COUNTY_CONFIGS = {
    'dv': {
        'county_name': 'dv',
        'url': 'https://core.duvalclerk.com/',
        'download_table_xpath': '//*[@id="c_DocketsPanel"]/div/table',
        'docket_row_tag_name': 'tbody',
        'case_type_xpath': '',
        'case_status_xpath': '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[4]/div/div[1]/table/tbody/tr[2]/td[2]',
        'files_page_url': 'https://core.duvalclerk.com/',
        'navigate_to_url': None,
        'navigate_to_search': None,
        'search_case_number': search_case_dv,
        'navigate_to_files': navigate_to_files_table_dv,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "[",
        'parties_table_xpath': "/html/body/form/div[3]/div/div[2]/div/div/div[4]/div/div[2]/div/table",
    },
    'oc': {
        'county_name': 'oc',
        'url': 'https://myeclerk.myorangeclerk.com/Cases/search',
        'download_table_xpath': '//*[@id="docketTable"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="headerCollapse"]/div/div[1]/div[2]',
        'case_status_xpath': '//*[@id="headerCollapse"]/div/div[6]/div[2]',
        'files_page_url': 'https://myeclerk.myorangeclerk.com/',
        'navigate_to_url': navigate_to_url_oc,
        'navigate_to_search': navigate_to_search_oc,
        'search_case_number': search_case_number_oc,
        'navigate_to_files': navigate_to_files_table_oc,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "Doc",
    },
    'lee': {
        'county_name': 'Lee',
        'url': 'https://matrix.leeclerk.org',
        'download_table_xpath': '//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="headerCollapse"]/div/div/table/tbody/tr/td[2]',
        'case_status_xpath': '//*[@id="headerCollapse"]/div/div/table/tbody/tr/td[3]',
        'files_page_url': 'https://matrix.leeclerk.org/',
        'navigate_to_url': navigate_to_url_lee,
        'navigate_to_search': navigate_to_search_lee,
        'search_case_number': search_case_number_lee,
        'navigate_to_files': navigate_to_files_table_lee,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "Doc",
    },
    'seminole': {
        'county_name': 'Seminole',
        'url': 'https://courtrecords.seminoleclerk.org/civil/',
        'download_table_xpath': '//*[@id="docketGrid"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="MainContent_case_type"]',
        'case_status_xpath': '//*[@id="MainContent_case_status"]',
        'files_page_url': 'https://courtrecords.seminoleclerk.org/',
        'navigate_to_url': navigate_to_url_seminole,
        'navigate_to_search': None,
        'search_case_number': search_case_number_seminole,
        'navigate_to_files': navigate_to_files_table_seminole,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "20",
    },
    'sarasota': {
        'county_name': 'Sarasota',
        'url': 'https://secure.sarasotaclerk.com/AnonLanding.aspx',
        'download_table_xpath': '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '',
        'case_status_xpath': '//*[@id="cphBody_CaseStatus"]',
        'files_page_url': 'https://secure.sarasotaclerk.com/',
        'navigate_to_url': navigate_to_url_sarasota,
        'navigate_to_search': navigate_to_search_sarasota,
        'search_case_number': search_case_number_sarasota,
        'navigate_to_files': navigate_to_files_table_sarasota,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "Clerk",
        'parties_table_xpath' : "/html/body/form/div[2]/div/table/tbody/tr/td[1]/div/div[2]/div/div[2]/main/fieldset[2]/div/table"
    },
    'manatee': {
        'county_name': 'Manatee',
        'url': 'https://records.manateeclerk.com/',
        'download_table_xpath': '//*[@id="dockets"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="content"]/div/div[3]/div[2]/div/div[2]/ul/li[2]/span[2]',
        'case_status_xpath': '//*[@id="content"]/div/div[3]/div[2]/div/div[2]/ul/li[1]/span[2]',
        'files_page_url': 'https://records.manateeclerk.com/CourtRecords/Case/Details',
        'navigate_to_url': navigate_to_url_manatee,
        'navigate_to_search': None,
        'search_case_number': None,
        'navigate_to_files': navigate_to_files_table_manatee,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "MC",
        'parties_table_xpath' : '//*[@id="content"]/div/div[4]/div[1]/div/div[2]/table'
    },
    'pb': {
        'county_name': 'pb',
        'url': 'https://appsgp.mypalmbeachclerk.com/eCaseView/search.aspx',
        'download_table_xpath': '//*[@id="docketTable"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '',
        'case_status_xpath': '',
        'files_page_url': 'https://appsgp.mypalmbeachclerk.com/',
        'navigate_to_url': navigate_to_url_pb,
        'navigate_to_search': navigate_to_search_pb,
        'search_case_number': enter_docket_number_pb,
        'navigate_to_files': navigate_to_files_pb,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "50",
        'file_prefix': "Clerk",
        'parties_table_xpath' : '//*[@id="infoTable"]',
        "show_parties_action": show_parties_pb,
        "show_docket_action": show_docket_pb,
    },
    'bw': {
        'county_name': 'bw',
        'url': 'https://www.browardclerk.org/Web2',
        'download_table_xpath': '//*[@id="tblEvents"]/tbody',
        'table_xpath2': '//*[@id="tblDispositionsCV"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="liCaseType"]',
        'case_status_xpath': '//*[@id="liCaseStatusNotCR"]',
        'files_page_url': 'https://www.browardclerk.org/',
        'navigate_to_url': navigate_to_url_bw,
        'navigate_to_search': navigate_to_search_bw,
        'search_case_number': search_case_number_bw,
        'navigate_to_files': navigate_to_files_table_bw,
        'step_timeouts': {'navigate_to_url': 30, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "MC",
    },
    'md': {
        'county_name': 'Miami Dade',
        'url': 'https://www2.miamidadeclerk.gov/UserManagementServices',
        'download_table_xpath': '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]',
        'docket_row_tag_name': 'div',
        'case_type_xpath': '//*[@id="content"]/div/div[5]/div/div[2]/div[1]/div/div[5]/div[2]',
        'case_status_xpath': '//*[@id="content"]/div/div[5]/div/div[2]/div[1]/div/div[5]/div[1]',
        'files_page_url': 'https://www2.miamidadeclerk.gov/',
        'navigate_to_url': navigate_to_url_md,
        'navigate_to_search': navigate_to_search_md,
        'search_case_number': search_case_number_md,
        'navigate_to_files': navigate_to_files_table_md,
        'username': 'karim.merchaoui@gmail.com',
        'password': 'MSVmsv123?',
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
    },
    'osceola': {
        'county_name': 'Osceola',
        'url': 'https://courts.osceolaclerk.com/',
        'download_table_xpath': '//*[@id="gridDockets"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="summaryAccordionCollapse"]/table/tbody/tr/td[3]/dl/dd[1]',
        'case_status_xpath': '',
        'files_page_url': 'https://courts.osceolaclerk.com/',
        'navigate_to_url': navigate_to_url_osceola,
        'navigate_to_search': navigate_to_search_osceola,
        'search_case_number': search_case_number_osceola,
        'navigate_to_files': navigate_to_files_table_osceola,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'parties_table_xpath' : '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[7]/div/div/div[2]/div/div/div/table'
    },
    'volusia': {
        'county_name': 'Volusia',
        'url': 'https://ccms.clerk.org/',
        'download_table_xpath': '//*[@id="GridDocket"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="caseTypelbl"]',
        'case_status_xpath': '//*[@id="status"]',
        'files_page_url': 'https://ccms.clerk.org/caseCM',
        'navigate_to_url': navigate_to_url_vs,
        'navigate_to_search': navigate_to_search_vs,
        'search_case_number': search_case_number_vs,
        'navigate_to_files': navigate_to_files_table_vs,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "load",
        'show_parties_table': show_parties_vs,
        'show_dockets_table': show_dockets_vs,
        'parties_table_xpath':'//*[@id="GridCaseParty"]'

    },
    'polk': {
        'county_name': 'Polk',
        'url': 'https://court.polk-county.net/',
        'download_table_xpath': '//*[@id="doctable"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="body"]/section/div[1]/div[5]/div[2]/div[1]/strong',
        'case_status_xpath': '//*[@id="body"]/section/div[1]/div[5]/div[2]/div[4]/strong',
        'files_page_url': 'https://pro.polkcountyclerk.net/',
        'navigate_to_url': navigate_to_url_polk,
        'navigate_to_search': navigate_to_search_polk,
        'search_case_number': search_case_number_polk,
        'navigate_to_files': navigate_to_files_table_polk,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 120, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "document",
        'parties_table_xpath': '//*[@id="partygridtable"]',
        'show_parties_table': show_parties_polk,
        'show_dockets_table': show_dockets_polk,
    },
    'brevard': {
        'county_name': 'Brevard',
        'url': 'https://vmatrix1.brevardclerk.us',
        'download_table_xpath': '//*[@id="tbl-content"]/tbody',
        'docket_row_tag_name': 'tr',
        'case_type_xpath': '//*[@id="inputForm"]/table[1]/tbody/tr[2]/td[2]',
        'case_status_xpath': '//*[@id="inputForm"]/table[1]/tbody/tr[2]/td[4]',
        'files_page_url': 'https://vmatrix1.brevardclerk.us/beca/all_results',
        'navigate_to_url': navigate_to_url_brevard,
        'navigate_to_search': navigate_to_search_brevard,
        'search_case_number': search_case_number_brevard,
        'navigate_to_files': None,
        'step_timeouts': {'navigate_to_url': 60, 'navigate_to_search': 60, 'search_case_number': 60,
                          'navigate_to_files': 60},
        'file_prefix': "Document",
        "parties_table_xpath": '//*[@id="inputForm"]/table[4]'
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

DOWNLOAD_FUNCTIONS = {
    'polk': trigger_download_polk,
    'oc': trigger_download_oc,
    'seminole': trigger_download_seminole,
    'lee': trigger_download_lee,
    'volusia': trigger_download_vs,
    'manatee': trigger_download_manatee,
    'brevard': trigger_download_brevard,
    'sarasota': trigger_download_sarasota,
    'dv': trigger_download_dv,
    'pb': trigger_download_pb,
    'osceola': trigger_download_osceola,
    'Miami Dade': trigger_download_miami,
    'bw': trigger_download_bw,
}


# ══════════════════════════════════════════════════════════════════════════════
# STEP VERIFIERS
# ══════════════════════════════════════════════════════════════════════════════

STEP_VERIFIERS = {
    'oc': {
        'navigate_to_url': lambda d: 'myorangeclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'caseNumber'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="caseList"]/tbody/tr/td'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="docketTable"]/tbody'),
    },
    'pb': {
        'navigate_to_url': None,
        'navigate_to_search': lambda d: element_exists_id(d, 'cphBody_gvSearch_txtParameter_0'),
        'search_case_number': lambda d: element_exists_id(d, 'cphBody_gvResults_lbCaseNumber_0'),
        'navigate_to_files': lambda d: element_exists_id(d, 'cphBody_lbDockets'),
    },
    'Lee': {
        'navigate_to_url': lambda d: 'leeclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'byCaseNumber_CaseNumber'),
        'search_case_number': lambda d: 'leeclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d,
                                                            '//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody'),
    },
    'Seminole': {
        'navigate_to_url': lambda d: 'seminoleclerk' in d.current_url,
        'navigate_to_search': None,
        'search_case_number': lambda d: element_exists_id(d, 'CaseNum') or element_exists_id(d, 'CaseGrid'),
        'navigate_to_files': lambda d: element_exists_id(d, 'collapseDockets'),
    },
    'Sarasota': {
        'navigate_to_url': lambda d: 'sarasotaclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'ctl00_cphBody_tbCaseNumber'),
        'search_case_number': lambda d: 'sarasotaclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody'),
    },
    'Manatee': {
        'navigate_to_url': lambda d: element_exists_id(d, 'CaseNumber'),
        'navigate_to_search': None,
        'search_case_number': None,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="dockets"]/tbody'),
    },
    'bw': {
        'navigate_to_url': lambda d: 'browardclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'CaseNumber'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="SearchResultsGrid"]'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="tblEvents"]/tbody'),
    },
    'Miami Dade': {
        'navigate_to_url': lambda d: 'miamidadeclerk' in d.current_url,
        'navigate_to_search': lambda d: 'miamidadeclerk' in d.current_url,
        'search_case_number': lambda d: 'miamidadeclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d,
                                                            '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]'),
    },
    'dv': {
        'navigate_to_url': lambda d: 'duvalclerk' in d.current_url,
        'navigate_to_search': None,
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="ContentPlaceHolder1_WebTab1"]'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="c_DocketsPanel"]/div/table'),
    },
    'Osceola': {
        'navigate_to_url': lambda d: 'osceolaclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'caseNumber'),
        'search_case_number': lambda d: 'osceolaclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="gridDockets"]/tbody'),
    },
    'Volusia': {
        'navigate_to_url': lambda d: 'clerk.org' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'Content1_CaseNum'),
        'search_case_number': lambda d: 'clerk.org' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="GridDocket"]/tbody'),
    },
    'Polk': {
        'navigate_to_url': None,
        'navigate_to_search': lambda d: element_exists_id(d, 'UCN'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="gridtable"]/tbody'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="doctable"]/tbody'),
    },
    'Brevard': {
        'navigate_to_url': lambda d: element_exists_xpath(d, '/html/body/form/table/tbody/tr[2]/td/center/input'),
        'navigate_to_search': lambda d: element_exists_xpath(d, '/html/body/form/div[1]'),
        'search_case_number': lambda d: 'brevardclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="tbl-content"]/tbody'),
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# VPN RESET COUNTIES
# ══════════════════════════════════════════════════════════════════════════════

VPN_RESET_COUNTIES = {'osceola'}


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _get_county_display_name(county_lower):
    for key, name in COUNTY_DISPLAY_NAMES.items():
        if key in county_lower:
            return name
    return county_lower.title()


def _get_verifier(county_name, step_name):
    """Return the verification lambda for a county+step, or None."""
    v = STEP_VERIFIERS.get(county_name)
    return v.get(step_name) if v else None
