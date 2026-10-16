# models.py
import os
from dataclasses import dataclass
from typing import Optional


def _clean_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    # Remove newlines and collapse multiple spaces
    return " ".join(value.replace("\n", " ").split())



@dataclass
class Case:
    year: str
    case_number: str
    county: str  # NOTE: historically holds the *processor* identifier (e.g. "new jersey", "orange", "broward") — kept as-is for backward compatibility with existing callers. Use `.processor_name` below to refer to this by its correct meaning.
    case_type: Optional[str] = "CA"  # Default to Civil Action if missing
    county_name: Optional[
        str] = None  # The ACTUAL county (e.g. "Burlington") — separate from `county` above, which is really the processor.

    def __post_init__(self):
        # Clean all string fields ONCE
        self.year = _clean_str(self.year)
        self.case_number = _clean_str(self.case_number)
        self.county = _clean_str(self.county)
        self.case_type = _clean_str(self.case_type)
        self.county_name = _clean_str(self.county_name)

    @property
    def processor_name(self) -> str:
        """
        Alias for `county`. The `county` field actually stores the processor /
        court-system identifier (e.g. "new jersey", "orange", "broward"), not
        a real county. Use this property when you mean the processor, and
        `county_name` when you mean the actual county.
        """
        return self.county

    @property
    def id(self) -> str:
        """
        The CLEAN ID used for your GUI, Dictionary Keys, and Folders.
        Format: 2023-CA-001234
        """
        c_lower = self.county.lower().strip() if self.county else ""
        if "broward" in c_lower:
            return f"{self.case_type}-{self.year}-{self.case_number}"
        if "orange" in c_lower:
            clean_num = str(self.case_number).strip()
            clean_year = str(self.year).strip()
            # Ensure we don't accidentally double-dash if case_type is missing
            ctype = f"{self.case_type}" if self.case_type else ""
            return f"{clean_year}-{ctype}-{clean_num}-O"
        if "lee" in c_lower or "miami" in c_lower or "pasco" in c_lower:
            return f"{self.year}-{self.case_type}-{self.case_number}"
        if "jersey" in c_lower or c_lower == "nj" or "nj" in c_lower.split():
            clean_num = str(self.case_number).strip()
            if clean_num.lower().startswith(("f-", "ch-")):
                return clean_num
            return f"f-{clean_num}-{self.year}"

        return f"{self.case_number.strip()}"

    @property
    def search_term(self) -> str:
        """
        The DIRTY ID used ONLY for the website search bar.
        Handles specific county quirks automatically.
        """
        c_lower = self.county.lower().strip() if self.county else ""

        if "seminole" in c_lower:
            # Seminole often wants: 2023CA001234 (No dashes)
            return f"{self.year}{self.case_type}{self.case_number}"

        if "polk" in c_lower:
            # Polk often just wants the number or Year-Number
            return f"{self.year}-{self.case_number}"

        if "jersey" in c_lower or c_lower == "nj" or "nj" in c_lower.split():
            # New Jersey needs just the docket number for the docket input field
            clean_num = str(self.case_number).strip()
            if clean_num.lower().startswith(("f-", "ch-")):
                parts = clean_num.split("-")
                if len(parts) >= 2:
                    return parts[1]
            return clean_num

        # Default fallback (Orange, Sarasota, etc.)
        return self.id

    def get_file_dir(self, final_output_folder: str) -> str:
        """
        Creates the full directory path based on county naming conventions.
        Replaces the logic previously found in _submit_single_case.
        """
        county_lower = self.county.lower().strip()

        if any(k in county_lower for k in ["jersey", "nj", "orange", "lee"]):
            # Format: f-docket-year-county
            folder_name = f"f-{self.case_number}-{self.year}"
        elif "broward" in county_lower:
            # Format: court_type-year-docket
            folder_name = f"{self.case_type}-{self.year}-{self.case_number}-{county_lower}"
        else:
            # Format: docket-county
            folder_name = f"{self.case_number}-{self.county}"

        return os.path.join(final_output_folder, folder_name)
