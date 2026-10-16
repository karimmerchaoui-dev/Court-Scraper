



import pysnooper

# ============================================================================
# CONSOLIDATED CONFIGURATION - Single source of truth
# ============================================================================

FILE_TRACKING_RULES = {
    "bankruptcy": {
        "flag_column": "Bankruptcy",
        "recent_column": "Recent Bankruptcy",
        "keywords": ["bankruptcy"],
        "rip_reason": "Bankruptcy Filed"  # Optional: marks case as RIP
    },
    "vacate": {
        "flag_column": "Vacate",
        "recent_column": "Recent Vacate",
        "keywords": ["vacate"],
        "rip_reason": "Motion to Vacate"
    },
    "cancel": {
        "flag_column": "Cancel",
        "recent_column": "Recent Cancel",
        "keywords": ["cancel"],
        "rip_reason": "Cancellation"
    },
    "certification_of_mailing": {
        "flag_column": "Certification of Mailing",
        "recent_column": "Recent Certification",
        "keywords": ["certification_of_mailing"]
    }
}

FIRST_FILE_RULES = [
    {
        "contains": "order_to_vacate",
        "status": "On Hold",
        "reason": "order_to_vacate"
    },
    {
        "contains": "foreclosure_dismissal_warning_notice",
        "status": "On Hold",
        "reason": "foreclosure_dismissal_warning_notice"
    },
    {
        "contains": "foreclosure_dismissal_order_notice",
        "status": "On Hold",
        "reason": "foreclosure_dismissal_order_notice"
    },
    {
        "contains": "stipulation_of_settlement_dismissal",
        "status": "On Hold",
        "reason": "stipulation_of_settlement_dismissal"
    },
    {
        "contains": "dismissal",
        "status": "RIP",
        "reason": "dismissal"
    }
]



import re


def extract_date_from_filename(filename):
    date_pattern = r'_(\d{2}_\d{2}_\d{4})_'
    match = re.search(date_pattern, filename)
    if match:
        return match.group(1)
    return None


def tick_keywords_all_dates(lower_files, case_id,report_cases,files_dir):
    
    with pysnooper.snoop(output=f"{files_dir}/keyword_dates.log"):
        if case_id not in report_cases:
            report_cases[case_id] = {}
        
        vacate_dates = []
        cancel_dates = []
        bankruptcy_dates = []
        order_to_stay_dates = []
        motion_to_stay_dates = []
        
        for filename in lower_files:
            filename_lower = filename.lower()
            file_date = extract_date_from_filename(filename_lower)
            
            if "vacate" in filename_lower:
                report_cases[case_id]['Vacate'] = "✅"
                if file_date:
                    vacate_dates.append(file_date)
            
            if "cancel" in filename_lower:
                report_cases[case_id]['Cancel'] = "✅"
                if file_date:
                    cancel_dates.append(file_date)
            
            if "bankruptcy" in filename_lower:
                report_cases[case_id]['Bankruptcy'] = "✅"
                if file_date:
                    bankruptcy_dates.append(file_date)
            
            if "order_to_stay" in filename_lower:
                report_cases[case_id]['Case status'] = "RIP"
                report_cases[case_id]['Order To Stay/Motion To Stay'] = "✅"
                if file_date:
                    order_to_stay_dates.append(file_date)
            
            if "motion_to_stay" in filename_lower:
                report_cases[case_id]['Case status'] = "RIP"
                report_cases[case_id]['Order To Stay/Motion To Stay'] = "✅"
                if file_date:
                    motion_to_stay_dates.append(file_date)
        
        # Set defaults
        for key in ['Vacate', 'Cancel', 'Bankruptcy', 'Order To Stay/Motion To Stay']:
            if key not in report_cases[case_id]:
                report_cases[case_id][key] = "❌"
        
        # Store all dates (as list or joined string)
        if vacate_dates:
            report_cases[case_id]['vacate_dates'] = vacate_dates
            report_cases[case_id]['vacate_date'] = vacate_dates[0]  # First occurrence
        if cancel_dates:
            report_cases[case_id]['cancel_dates'] = cancel_dates
            report_cases[case_id]['cancel_date'] = cancel_dates[0]
        if bankruptcy_dates:
            report_cases[case_id]['bankruptcy_dates'] = bankruptcy_dates
            report_cases[case_id]['bankruptcy_date'] = bankruptcy_dates[0]
        if order_to_stay_dates:
            report_cases[case_id]['order_to_stay_dates'] = order_to_stay_dates
            report_cases[case_id]['order_to_stay_date'] = order_to_stay_dates[0]
        if motion_to_stay_dates:
            report_cases[case_id]['motion_to_stay_dates'] = motion_to_stay_dates
            report_cases[case_id]['motion_to_stay_date'] = motion_to_stay_dates[0]


FILE_RULES = {
    "flags": {
        "bankruptcy": "bankruptcy",
        "vacate": "vacate",
        "cancel": "cancel",
        "certification_of_mailing": "certification_of_mailing"
    },
    "rip_rules": {
        "Bankruptcy Filed": "bankruptcy",
        "Motion to Vacate": "vacate",
        "Cancellation": "cancel"
    }
}

def apply_file_rules(matching_rows, case_id, report_cases):
    """
    Applies all file-based rules and mutates report_cases[case_id].
    Returns pruned matching_rows.
    """
    lower_files = [f["filename"].lower() for f in matching_rows]

    # ---------- flags ----------
    for col, keyword in FILE_RULES["flags"].items():
        report_cases[case_id][col] = "✅" if any(keyword in f for f in lower_files) else "❌"
        report_cases[case_id][f"Recent {col}"] = ""

    # ---------- RIP rules ----------
    for reason, keyword in FILE_RULES["rip_rules"].items():
        if any(keyword in f for f in lower_files):
            #report_cases[case_id]["Case status"] = "RIP"
            report_cases[case_id]["Order To Stay/Motion To Stay"] = "✅"
            report_cases[case_id]["Reason"] = reason
            break
    else:
        report_cases[case_id]["Order To Stay/Motion To Stay"] = "❌"

    return matching_rows

def process_additional_sums(lower_files,case_id,report_cases):
    matching_elements = [item for item in lower_files if "additional_sums" in item.lower()]
    if matching_elements:
        count = len(matching_elements)
        report_cases[case_id]['additional sums files'] = matching_elements
        report_cases[case_id]['additional_sums_count'] = count
    else:
        print("No elements containing 'additional sums' found.")
        report_cases[case_id]['additional_sums_count'] = "0"



def apply_first_file_rules(first_file, case_id,report_cases):

    if not first_file:
        return False

    name = first_file.lower()

    for rule in FIRST_FILE_RULES:
        if rule["contains"] in name:
            #report_cases[case_id]["Case status"] = rule["status"]
            if rule["reason"]:
                report_cases[case_id]["Reason"] = rule["reason"]
            return True  # stop at first match

    return False


def process_all_file_rules(matching_rows, case_id, report_cases,files_dir):
    """
    Single function that processes all file-based rules.
    Replaces: tick_keywords, apply_file_rules, apply_file_tracking_rules
    """
    if not matching_rows:
        initialize_empty_report(case_id, report_cases)
        return matching_rows

    lower_files = [f["filename"].lower() for f in matching_rows]

    # 1. Process additional sums
    process_additional_sums(lower_files, case_id, report_cases)

    # 2. Apply file tracking rules (bankruptcy, vacate, cancel, etc.)
    apply_unified_tracking_rules(matching_rows, case_id, report_cases)

    # 3. Apply first file rules (dismissal, etc.)
    first_file = matching_rows[0]["filename"]
    apply_first_file_rules(first_file, case_id, report_cases)

    tick_keywords_all_dates(lower_files,case_id,report_cases,files_dir)
    return matching_rows


def initialize_empty_report(case_id, report_cases):
    """Initialize all columns when no files found"""
    report_cases[case_id]["Order To Stay/Motion To Stay"] = "❌"

    for rule in FILE_TRACKING_RULES.values():
        report_cases[case_id][rule["flag_column"]] = "❌"
        report_cases[case_id][rule["recent_column"]] = ""

    report_cases[case_id]['additional_sums_count'] = "0"


def apply_unified_tracking_rules(matching_rows, case_id, report_cases):
    """
    Unified tracking: sets flags, recent files, and RIP status.
    Replaces both apply_file_rules and apply_file_tracking_rules.
    """
    lower_files = [f["filename"].lower() for f in matching_rows]
    rip_detected = False

    for rule_name, rule in FILE_TRACKING_RULES.items():
        flag_col = rule["flag_column"]
        recent_col = rule["recent_column"]
        keywords = rule["keywords"]

        # Check if any file matches
        has_match = any(
            any(keyword in filename for keyword in keywords)
            for filename in lower_files
        )

        # Set flag
        report_cases[case_id][flag_col] = "✅" if has_match else "❌"

        # Find most recent file
        if has_match:
            for file_data in matching_rows:
                filename = file_data["filename"]
                if any(keyword in filename.lower() for keyword in keywords):
                    report_cases[case_id][recent_col] = filename

                    # Check if this triggers RIP status
                    if "rip_reason" in rule and not rip_detected:
                        #report_cases[case_id]["Case status"] = "RIP"
                        report_cases[case_id]["Order To Stay/Motion To Stay"] = "✅"
                        report_cases[case_id]["Reason"] = rule["rip_reason"]
                        rip_detected = True
                    break
        else:
            report_cases[case_id][recent_col] = ""

    # Set Order To Stay if not already set by RIP
    if "Order To Stay/Motion To Stay" not in report_cases[case_id]:
        report_cases[case_id]["Order To Stay/Motion To Stay"] = "❌"

