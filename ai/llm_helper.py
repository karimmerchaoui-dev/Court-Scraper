import hashlib
import json
import os
import re
import time
import traceback
from typing import List, Optional

import anthropic
import pysnooper
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq
from mistralai import Mistral
from mistralai.models.sdkerror import SDKError
from pydantic import BaseModel, Field

load_dotenv()
mistral_api = os.getenv("MISTRAL_API_KEY", "")

try:
    from ai.ocr import pdf_to_text
except ModuleNotFoundError:
    try:
        from ocr import pdf_to_text
    except ModuleNotFoundError:
        from .ocr import pdf_to_text


class Defendant(BaseModel):
    name: Optional[str] = None
    defendant_number: Optional[str] = None
    address: Optional[str] = None
    relationship: Optional[str] = None


class Plaintiff(BaseModel):
    name: Optional[str] = None


class Lien(BaseModel):
    lienholder: Optional[str] = None
    lien_type: Optional[str] = None
    amount: Optional[str] = None
    recording_date: Optional[str] = None
    instrument_number: Optional[str] = None


from typing import Optional

from pydantic import BaseModel


class FinalJudgmentData(BaseModel):
    case_number: Optional[str] = None
    plaintiff: Optional[str] = None
    defendants: List[str] = []
    property_address: Optional[str] = None
    judgment_date: Optional[str] = None
    final_judgment_amount: Optional[str] = None
    judgment_interest: Optional[str] = None
    total_final_judgment_amount: Optional[str] = None
    sales_date: Optional[str] = None
    auction_time: Optional[str] = None


class JudgmentAmount(BaseModel):
    interest: Optional[str] = None
    total_judgment_amount: Optional[str] = None


class AuctionInfo(BaseModel):
    sales_date: Optional[str] = None
    sale_time: Optional[str] = None


class DeceasedPerson(BaseModel):
    name: str | None = None
    date_of_death: str | None = None
    evidence_text: str | None = None


class ForeclosureExtraction(BaseModel):
    final_judgment_amount: float | None
    sales_date: str | None



def extract_judgment_info(driver) -> dict:
    """
    Extracts the total final judgment amount and foreclosure sale date
    from the currently loaded Selenium page.

    Returns:
    {
        "final_judgment_amount": float | None,
        "sales_date": str | None
    }
    """

    html = driver.page_source

    soup = BeautifulSoup(html, "lxml")

    # Remove useless elements
    for tag in soup(["script", "style", "svg", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)

    # Collapse blank lines
    text = "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    )

    # Prevent huge prompts
    text = text[:100000]


    prompt = f"""
You are extracting information from a foreclosure court docket.

Rules:

- ONLY use information explicitly present.
- Do NOT calculate or infer.
- If the page only says "Final Judgment" but no amount, return null.
- The judgment amount is usually called:
    - Final Judgment Amount
    - Judgment Amount
    - Total Judgment
    - Plaintiff shall recover
    - Total Due
    - Amount Due
- The sale date may appear as:
    - Auction Date
    - Sale Date
    - Foreclosure Sale
    - Notice of Sale
    - Judicial Sale

Return valid JSON only.

PAGE:

{text}
"""
    raw = call_unified_llm(
                prompt=prompt,
                system_prompt="You are an obituary information extraction engine. Return ONLY valid JSON matching the requested schema.",
                response_json=True,
                service="anthropic",
                api_key=os.getenv("SUPABASE_URL"),
                model="claude-haiku-4-5-20251001",
                task="obituary",
            )

    try:
        return raw
    except Exception:
        return {
            "final_judgment_amount": None,
            "sales_date": None,
        }

@pysnooper.snoop()
def extract_final_judgment(file_path, service=None, api_key=None, model=None):
    final_judg_text = pdf_to_text(file_path)
    final_judg_prompt = f"""
    Extract information from this Final Judgment of Foreclosure.

    Rules:
    - Extract only information explicitly stated in the document.
    - Do not infer or guess.
    - Return null for missing values.
    - Return valid JSON matching the provided schema.
    - Preserve dates exactly as written.
    - Preserve monetary amounts exactly as written.

    Extract:

    1. Case number
    2. Plaintiff
    3. Defendants
    4. Property address
    5. Judgment date
    6. Total final judgment amount
    8. Auction sale date
    9. Auction sale time

    Notes:
    - The final judgment amount is usually labeled as:
    "Total Judgment", "Final Judgment Amount",
    "Amount Due", "Total Amount Due", or similar.
    - The interest amount should be extracted separately if stated.
    - The auction date may be called:
    "Sale Date", "Foreclosure Sale Date",
    "Judicial Sale Date", "Auction Date",
    or "Date of Sale".
    - The auction time may be called:
    "Sale Time", "Auction Time",
    or appear in the sale scheduling section.

    Document:

    {final_judg_text}
    """
    try:
        from app import _settings
        cfg = _settings.get("llm_configs", {}).get("judgment", {}) if isinstance(_settings.get("llm_configs"), dict) else {}
    except Exception:
        cfg = {}

    svc = service or cfg.get("service")
    key = api_key or cfg.get("api_key")
    mdl = model or cfg.get("model")

    raw = call_unified_llm(
        prompt=final_judg_prompt,
        system_prompt="You are a legal document analyst specializing in foreclosure final judgments. Return valid JSON only.",
        response_json=True,
        service=svc,
        api_key=key,
        model=mdl,
        schema=FinalJudgmentData.model_json_schema(),
        task="judgment"
    )
    try:
        return json.loads(raw)
    except Exception:
        return raw

##################################################
"""
extract_complaint, migrated from Mistral (mistral-small-2506) to
Claude Haiku 4.5, with the same token-reduction principles as the
bankruptcy-status function:

  1. Forced tool-use for structured output instead of free-form JSON-in-prose.
     This is a strict upgrade, not a tradeoff: Anthropic's tool-use forcing
     guarantees schema-conformant output (mirrors what Mistral's
     response_format schema was doing) AND tends to produce fewer output
     tokens than "return JSON matching this schema" in prose, since there's
     no room for the model to add narration around the JSON.
  2. Instructions reworded for density, not content. Every extraction rule,
     every edge case (deceased-person naming, address variability, block/lot
     formats) is still there -- only the phrasing is tighter. Rough sizes:
     ~1,000 tokens (original wording) -> ~530 tokens (below).
  3. Result memoization by content hash, so re-processing the same document
     (retries, reruns, duplicate uploads) costs $0 instead of a fresh call.
  4. Header/footer stripping via the same clean_pdf_text() used for the
     bankruptcy function -- reuse it if you're already importing it there.

NOTE ON CACHING: not used here. Even the *original*, unshortened instructions
block is only ~1,000 tokens -- well under the 4,096-token minimum Anthropic
requires before a cache_control block does anything on Claude Haiku 4.5.
Adding cache_control here would silently do nothing, so it's left out.
"""

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are a legal document analyst extracting structured data from "
    "foreclosure complaints. Use only information explicitly stated in the "
    "document -- never guess or infer beyond what's written."
)

COMPLAINT_INSTRUCTIONS_BLOCK = """Extract data from this foreclosure complaint. Only use information explicitly stated -- never guess or infer. Missing values = null. Return JSON matching the schema.

EXTRACT:
- All plaintiffs and defendants (with defendant numbers and addresses if listed).
- Defendant relationships: spouse, heir, unknown tenant, occupant, trustee, borrower, co-borrower, personal representative.
- Mortgage execution date, amount owed, original mortgage amount, interest rate (if stated).
- All liens/judgments/tax liens/HOA liens/municipal liens/subordinate mortgages, each with lienholder, amount, date, recording info (where available).

DECEASED HOMEOWNER (homeowner_deceased is REQUIRED, always true or false, never null):
- true only with explicit indication (e.g. "deceased", "late", "estate of", "heir"). Otherwise false.
- If true: extract full name of deceased (do not infer from heirs alone -- "Estate of John Smith" or "Unknown Heirs of John Smith" both mean the deceased's name is "John Smith"), date of death if stated, and the exact text indicating death. List all deceased persons if more than one.

PROPERTY ADDRESS (extract precisely):
- Look for "property address", "property located at", "premises", "subject property", "commonly known as", the caption/case title, or a Schedule A/Exhibit A section.
- Combine multi-line or split (street / city-state) addresses into one. Formats vary in state abbreviation and ZIP/ZIP+4 presence.
- Fields: property_address, property_city, property_state (usually NJ), property_zip.

BLOCK AND LOT:
- Look for "Block"/"Lot" (any case), plus "Qualifier"/"Q"/"C" if present, in the property description, legal description, or schedule/exhibit sections. Formats vary (e.g. "Block 123, Lot 456", "Block 123.01, Lot 456.07, Qualifier C").
- Preserve exact formatting (e.g. "123.01"). If the legal description is complex, also extract it in full.
- If only block or only lot is found, extract what's available. If neither, set to null. Never infer from other fields.
- Fields: block, lot.

If block/lot or address appear in multiple places, use the most specific instance.

Document:
"""

TOOL_NAME = "extract_foreclosure_complaint"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_path(log_dir: str, doc_hash: str) -> str:
    return os.path.join(log_dir, f"complaint_cache_{doc_hash}.json")







"""def extract_complaint(file_path, service=None, api_key=None, model=None):
    log_dir = os.path.join(os.path.dirname(file_path), "llm_helper_logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"extract_complaint_{os.path.basename(os.path.dirname(file_path))}.log"
    )
    data_file = os.path.join(
        log_dir, f"complaint_extracted_data_{os.path.basename(os.path.dirname(file_path))}.txt"
    )

    complaint_text = pdf_to_text(file_path)  # noqa: F821 - your existing extractor

    # --- Memoization: skip the API call entirely for a document we've
    # already extracted (retries, reruns, duplicate uploads). ---
    doc_hash = _content_hash(complaint_text)
    cache_file = _cache_path(log_dir, doc_hash)
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cached = f.read()
        with open(data_file, "w") as f:
            f.write(cached)
        return cached

    try:
        from app import _settings
        cfg = _settings.get("llm_configs", {}).get("complaint", {}) if isinstance(_settings.get("llm_configs"), dict) else {}
    except Exception:
        cfg = {}

    svc = (service or cfg.get("service") or "anthropic").lower().strip()
    key = api_key or cfg.get("api_key") or ""
    mdl = model or cfg.get("model") or ""

    schema = ForeclosureComplaint.model_json_schema()

    prompt = f"{INSTRUCTIONS_BLOCK}\n\nDocument:\n{complaint_text}"
    raw = call_unified_llm(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        response_json=True,
        service=svc,
        api_key=key,
        model=mdl,
        schema=schema,
        task="complaint"
    )
    with open(data_file, "w") as f:
        f.write(raw)
    with open(cache_file, "w") as f:
        f.write(raw)
    return raw"""

def extract_complaint(file_path, service=None, api_key=None, model=None):
    """Extract foreclosure complaint data using configured LLM (Anthropic Haiku, Groq, OpenRouter, Google)."""
    log_dir = os.path.join(os.path.dirname(file_path), "llm_helper_logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"extract_complaint_{os.path.basename(os.path.dirname(file_path))}.log"
    )
    data_file = os.path.join(
        log_dir, f"complaint_extracted_data_{os.path.basename(os.path.dirname(file_path))}.txt"
    )

    complaint_text = pdf_to_text(file_path)  # noqa: F821 - your existing extractor

    # --- Memoization: skip the API call entirely for a document we've
    # already extracted (retries, reruns, duplicate uploads). ---
    doc_hash = _content_hash(complaint_text)
    cache_file = _cache_path(log_dir, doc_hash)
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cached = f.read()
        with open(data_file, "w") as f:
            f.write(cached)
        return cached

    try:
        from app import _settings
        cfg = _settings.get("llm_configs", {}).get("complaint", {}) if isinstance(_settings.get("llm_configs"), dict) else {}
    except Exception:
        cfg = {}

    svc = (service or cfg.get("service") or "anthropic").lower().strip()
    key = api_key or cfg.get("api_key") or ""
    mdl = model or cfg.get("model") or ""

    schema = ForeclosureComplaint.model_json_schema()

    prompt = f"{COMPLAINT_INSTRUCTIONS_BLOCK}\n\nDocument:\n{complaint_text}"
    raw = call_unified_llm(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        response_json=True,
        service=svc,
        api_key=key,
        model=mdl,
        schema=schema,
        task="complaint"
    )
    with open(data_file, "w") as f:
        f.write(raw)
    with open(cache_file, "w") as f:
        f.write(raw)
    return raw
##################################################

def extract_bv_data(report_text):
    bv_prompt = f"""
You are a data extraction assistant. Parse the following property owner report and return a strictly structured JSON dictionary with all the information. Follow the schema exactly.

Report:

    {report_text}
    """

    client = get_mistral_client()
    response = client.chat.complete(
        model="mistral-small-2506",
        messages=[
            {
                "role": "user",
                "content": bv_prompt
            }
        ],
        response_format={
            "type": "json_object"
        }
    )
    return response.choices[0].message.content


class ForeclosureComplaint(BaseModel):
    plaintiffs: List[Plaintiff] = []
    defendants: List[Defendant] = []

    property_address: Optional[str] = None

    mortgage_date: Optional[str] = None
    mortgage_amount: Optional[str] = None

    amount_owed: Optional[str] = None

    liens: List[Lien] = []

    case_number: Optional[str] = None
    filing_date: Optional[str] = None
    county: Optional[str] = None
    interest_rate: Optional[str] = None
    homeowner_deceased: bool = False
    deceased_persons: list[DeceasedPerson] = []
    property_address: Optional[str] = Field(None, description="Full property address")
    property_city: Optional[str] = Field(None, description="City of the property")
    property_state: Optional[str] = Field(None, description="State of the property (usually NJ)")
    property_zip: Optional[str] = Field(None, description="ZIP code of the property")

    # Block and lot fields
    block: Optional[str] = Field(None, description="Block number of the property")
    lot: Optional[str] = Field(None, description="Lot number of the property")

    # Legal description
    legal_description: Optional[str] = Field(None, description="Full legal description of the property")


from typing import List, Optional

from pydantic import BaseModel


# Python example using Mistral API with structured outputs


final_judg_text = ""
final_judg_prompt = f"""
Extract information from this Final Judgment of Foreclosure.

Rules:
- Extract only information explicitly stated in the document.
- Do not infer or guess.
- Return null for missing values.
- Return valid JSON matching the provided schema.
- Preserve dates exactly as written.
- Preserve monetary amounts exactly as written.

Extract:

1. Case number
2. Plaintiff
3. Defendants
4. Property address
5. Judgment date
6. Total final judgment amount
8. Auction sale date
9. Auction sale time

Notes:
- The final judgment amount is usually labeled as:
  "Total Judgment", "Final Judgment Amount",
  "Amount Due", "Total Amount Due", or similar.
- The interest amount should be extracted separately if stated.
- The auction date may be called:
  "Sale Date", "Foreclosure Sale Date",
  "Judicial Sale Date", "Auction Date",
  or "Date of Sale".
- The auction time may be called:
  "Sale Time", "Auction Time",
  or appear in the sale scheduling section.

Document:

{final_judg_text}
"""



# ─────────────────────────────────────────────
# USAGE
# ─────────────────────────────────────────────


class Address(BaseModel):
    street: str
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    addresses: List[Address]


# Python example using Mistral API with structured outputs


class FamilyMember(BaseModel):
    name: str
    relationship: str  # e.g., "spouse", "son", "daughter", "parent"


class ObituaryData(BaseModel):
    full_name: str = Field(description="Complete name of the deceased")
    birth_date: Optional[str] = Field(description="Date of birth in YYYY-MM-DD format if possible")
    death_date: Optional[str] = Field(description="Date of death in YYYY-MM-DD format if possible")
    age: Optional[int] = Field(description="Age at time of death")
    birth_location: Optional[str] = Field(description="Place of birth")
    residence: Optional[str] = Field(description="Last known residence")
    occupation: Optional[str] = Field(description="Primary occupation or career")
    education: Optional[List[str]] = Field(description="Educational institutions and degrees")
    military_service: Optional[str] = Field(description="Military service details")
    survived_by: Optional[List[FamilyMember]] = Field(description="Surviving family members")
    predeceased_by: Optional[List[FamilyMember]] = Field(description="Family who died before them")
    achievements: Optional[List[str]] = Field(description="Notable accomplishments")
    hobbies_interests: Optional[List[str]] = Field(description="Personal interests")
    memberships: Optional[List[str]] = Field(description="Organizations and clubs")
    funeral_date: Optional[str] = Field(description="Date of funeral service")
    funeral_location: Optional[str] = Field(description="Location of funeral service")
    burial_location: Optional[str] = Field(description="Cemetery or final resting place")
    charitable_donations: Optional[List[str]] = Field(description="Requested memorial charities")
    additional_notes: Optional[str] = Field(description="Other relevant information")


# Usage
import os

#
#
#
#
MISTRAL_KEYS = [
    "mstrl_kg9XwVeViQ4r69G6etElqmeeEEya77fT_2z3cff"
]


def get_mistral_client():
    last_error = None

    for api_key in MISTRAL_KEYS:
        for attempt in range(1, 4):  # 3 tries per key
            try:
                client = Mistral(api_key=api_key)
                client.models.list()
                return client

            except SDKError:
                print(f"Mistral SDK Error on key ...{api_key[-6:]} attempt {attempt}/3")
                continue

            except Exception as e:
                error_text = str(e).lower()
                if "401" in error_text or "unauthorized" in error_text or "429" in error_text:
                    print(f"Mistral key ...{api_key[-6:]} rejected on attempt {attempt}/3")
                    last_error = e
                    continue
                raise  # non-auth errors bubble up immediately

        # exhausted 3 attempts on this key — move to next
        print(f"Key ...{api_key[-6:]} failed all 3 attempts, switching to next key...")

    # shuffle and retry once more across all keys before giving up
    shuffled = MISTRAL_KEYS[:]
    random.shuffle(shuffled)
    for api_key in shuffled:
        try:
            client = Mistral(api_key=api_key)
            client.models.list()
            return client
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"All Mistral API keys failed. Last error: {last_error}")

def get_obituary_link_data(obituary_text, service=None, api_key=None, model=None):
    prompt = f"""
Extract the following information from this obituary.

Return ONLY a JSON object matching the provided schema.

Field definitions:

- name:
    The full legal name of the deceased.

- date_of_birth:
    Date of birth of the deceased, if explicitly stated.

- place_of_birth:
    City, state/province, or country where the deceased was born.

- date_of_death:
    Date of death of the deceased, if explicitly stated.

- place_of_death:
    City, state/province, or country where the deceased died.

- heirs:
    Return an array of objects, where each object contains:
    - "name": the person's full name.
    - "relationship": their relationship to the deceased (e.g., spouse, son, daughter, grandson, sister, father, mother).
    Include immediate heirs or legal successors explicitly mentioned in the obituary.

- associates:
    Return an array of objects, where each object contains:
    - "name": the person's full name.
    - "relationship": their relationship to the deceased (e.g., niece, nephew, cousin, aunt, uncle, in-law, caregiver, etc.).
    Include relatives or significant associates who are not direct heirs.

- friends:
    Return an array of objects, where each object contains:
    - "name": the person's full name.
    - "relationship": how they are described in the obituary (e.g., friend, lifelong friend, neighbor, coworker, classmate, church member, companion).
    Include only non-family individuals explicitly mentioned.

Rules:
- Do NOT infer information that is not explicitly stated.
- If a field is missing, return null.
- Arrays must be empty [] if no people are found.
- Return ONLY valid JSON.

Obituary:

{obituary_text}
"""

    try:
        raw = call_unified_llm(
            prompt=prompt,
            system_prompt="You are an obituary information extraction engine. Return ONLY valid JSON matching the requested schema.",
            response_json=True,
            service=service,
            api_key=api_key,
            model=model,
            task="obituary",
        )
        return json.loads(raw), obituary_text
    except Exception as e:
        print(f"[get_obituary_link_data] Error via unified LLM: {e}, attempting Mistral fallback...")
        client = get_mistral_client()
        response = client.chat.complete(
            model="mistral-small-2506",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object", "schema": ObituaryData.model_json_schema()}
        )
        return json.loads(response.choices[0].message.content), obituary_text


def get_bankruptcy_case_status(bankruptcy_path, service=None, api_key=None, model=None):
    bankruptcy_text = pdf_to_text(bankruptcy_path)
    bankruptcy_status_prompt = f"""
    You are a legal document analyst specializing in New Jersey foreclosure and bankruptcy proceedings.

    Analyze the document and determine whether the bankruptcy case was ACCEPTED or DENIED by the court.

    DEFINITIONS:
    - "accepted": the bankruptcy case is active and pending. The court has NOT dismissed it.
        Look for: notice of filing, certification of bankruptcy with no dismissal, PACER "Date Closed" blank.
    - "denied": the bankruptcy case was dismissed, denied, or closed without a discharge.
        Look for: order dismissing petition, order denying confirmation, pre-confirmation dismissal,
        PACER "Date Closed" with a date, or language stating the case "was dismissed."

    Also determine if foreclosure can proceed right now, based on this document:
    - "yes": either (a) the bankruptcy case was denied/dismissed/closed, OR
            (b) relief from the automatic stay was granted for this specific property
            (even if the bankruptcy case itself remains open).
    - "no": the bankruptcy case was accepted and is still open, AND no relief from stay has been granted —
            the automatic stay is still blocking action.

    IMPORTANT DISTINCTIONS:
    - An "Order Granting Relief from the Automatic Stay" does NOT mean the bankruptcy
    case was denied. It means the stay was lifted only as to the named property,
    while the bankruptcy case itself remains accepted/open. In this situation:
        - bankruptcy_case_status = "accepted"
        - foreclosure_permitted = "yes"

    - A "Certification of Bankruptcy Discharge" or similar filing title does not by
    itself mean the case was denied — read the body of the document to see
    what it actually certifies. It may instead be certifying relief from stay.

    - A prior bankruptcy case that was closed (e.g., from 2004) does NOT mean the
    current case is denied. Focus on the current case only.

    - An "Order to Show Cause Why Case Should Not Be Dismissed" is NOT a dismissal.
    The case is still accepted/open until a dismissal order is actually entered.

    ---

    INSTRUCTIONS FOR OUTPUT:
    Return a valid JSON object with these keys:
    - "bankruptcy_case_status": "accepted" or "denied"
    - "foreclosure_permitted": "yes" or "no"
    - "basis": brief description of what specifically permits/blocks foreclosure
    (e.g., "relief from stay granted", "case denied/dismissed", "case discharged",
    "automatic stay still in effect")
    - "justification": 2-4 sentences citing specific evidence from the document
    - "case_number": the bankruptcy case number if found, otherwise null
    - "relevant_date": the dismissal date, discharge date, or stay relief date,
    whichever applies, otherwise null
    - "confidence": 0-100

    Do not include any text outside the JSON object.

    ---

    DOCUMENT CONTENT TO ANALYZE:
    {bankruptcy_text}
    """
    try:
        from app import _settings
        cfg = _settings.get("llm_configs", {}).get("bankruptcy", {}) if isinstance(_settings.get("llm_configs"), dict) else {}
    except Exception:
        cfg = {}

    svc = service or cfg.get("service")
    key = api_key or cfg.get("api_key")
    mdl = model or cfg.get("model")

    return call_unified_llm(
        prompt=bankruptcy_status_prompt,
        system_prompt="You are a legal document analyst specializing in New Jersey foreclosure and bankruptcy proceedings. Return valid JSON only.",
        response_json=True,
        service=svc,
        api_key=key,
        model=mdl,
        task="bankruptcy"
    )



SYSTEM_PROMPT = """You are a legal document analyst specializing in real estate foreclosure records.

Your task is to extract ALL Book/Page pairs from court documents and return them as a JSON list.

## Extraction Rules:
- Strip any "OR-" prefix from book numbers
- Strip leading zeros from page numbers (e.g. "045" → "45")
- "at page", "at Page", "Page", "page" are all valid separators
- Commas between book and page are optional
- ONLY return book/page pairs — ignore instrument numbers like "F003259-22"
- If nothing is found, return an empty list

## Output format:
Return ONLY a JSON object: {"deed_records": [...]}

## Examples of some formats you may encounter:

Input: "Book 12417 Page 353"
Output: {"deed_records": [{"book": "12417", "page": "353"}]}

Input: "Book 12526 at page 495"
Output: {"deed_records": [{"book": "12526", "page": "495"}]}

Input: "Book 4118, Page 045"
Output: {"deed_records": [{"book": "4118", "page": "45"}]}

Input: "Book 4118 at Page 45"
Output: {"deed_records": [{"book": "4118", "page": "45"}]}

Input: "F003259-22"
Output: {"deed_records": []}

Input: "Book OR-8488, Page 9305"
Output: {"deed_records": [{"book": "8488", "page": "9305"}]}

Input: "Book OR-9180, Page 510"
Output: {"deed_records": [{"book": "9180", "page": "510"}]}

Input: "Book OR-9235, Page 1990"
Output: {"deed_records": [{"book": "9235", "page": "1990"}]}

Input: "Book OR-9581, Page 333"
Output: {"deed_records": [{"book": "9581", "page": "333"}]}

Input: "Book OR-9063,Page 4288"
Output: {"deed_records": [{"book": "9063", "page": "4288"}]}

Input: "Book OR-9174, Page 6806"
Output: {"deed_records": [{"book": "9174", "page": "6806"}]}

Input: "Book OR-8563, Page 7381"
Output: {"deed_records": [{"book": "8563", "page": "7381"}]}

Input: "Book 4560, Page 89"
Output: {"deed_records": [{"book": "4560", "page": "89"}]}

Input: "Book 4620, page 1541"
Output: {"deed_records": [{"book": "4620", "page": "1541"}]}

Input: "Book 2007, Page 1992"
Output: {"deed_records": [{"book": "2007", "page": "1992"}]}

Input: "Book 15120 Page 12"
Output: {"deed_records": [{"book": "15120", "page": "12"}]}

Input: "Book 414 at Page 122"
Output: {"deed_records": [{"book": "414", "page": "122"}]}

Input: "Book 6223 at Page 203"
Output: {"deed_records": [{"book": "6223", "page": "203"}]}

Input: "Book 6230 at Page 18"
Output: {"deed_records": [{"book": "6230", "page": "18"}]}

## Multiple entries example:
Input: "...Mortgage recorded in Book OR-9063,Page 4288 of the public records... also see Book 12417 Page 353 for the assignment..."
Output: {"deed_records": [{"book": "9063", "page": "4288"}, {"book": "12417", "page": "353"}]}"""

# ── Schema ────────────────────────────────────────────────────────────────────

class DeedRecord(BaseModel):
    book: str
    page: str


class ForeclosureExtractionResult(BaseModel):
    deed_records: list[DeedRecord] = Field(default_factory=list)


# ── Function ──────────────────────────────────────────────────────────────────

def get_deed_infos(pdf_path: str) -> ForeclosureExtractionResult:
    court_document_text = pdf_to_text(pdf_path)
    print(f"court_document_text : {court_document_text}")
    client = Mistral(api_key=mistral_api)
    response = client.chat.complete(
        model="mistral-small-2506",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"Extract all Book/Page pairs from this document:\n\n{court_document_text}"
            }
        ],
        response_format={
            "type": "json_object",
            "schema": ForeclosureExtractionResult.model_json_schema()
        }
    )

    raw = response.choices[0].message.content
    return ForeclosureExtractionResult(**json.loads(raw))


def add_deeds_to_report(complaint_path, report_cases, case_id):
    result = get_deed_infos(complaint_path)
    deed_records = result.deed_records
    # Store deeds under a dedicated key
    report_cases[case_id]["_deeds"] = [
        (deed.book, deed.page) for deed in deed_records
    ]
    return deed_records


def extract_obituary_paragraph_data(obituary_text: str) -> dict:
    """
    Utilizes Mistral LLM with strict JSON schema validation to extract
    highly granular biographical matrices out of unstructured obituary text.
    """
    if not obituary_text or not obituary_text.strip():
        return {}

    client = get_mistral_client()

    system_prompt = (
        "You are an expert data extraction assistant specialized in legal and genealogical records.\n"
        "Your task is to analyze the provided obituary text and extract key metadata into the requested JSON schema.\n\n"
        "STRICT EXTRACTION RULES:\n"
        "1. Normalized Dates: Convert all textual dates (e.g., 'December 21, 2006' or 'Jan 5th, 1944') strictly into ISO standard 'YYYY-MM-DD'. If the year is ambiguous or missing, output null.\n"
        "2. Missing Fields: If a specific piece of information (like place_of_birth) is not mentioned in the text, set its value to null. Never make up or assume data.\n"
        "3. Explicit Classification:\n"
        "   - heirs: Spouses, children, siblings, or direct surviving family members.\n"
        "   - associates: Mentioned employers, legal representatives, business relationships, or past coworkers.\n"
        "   - friends: People explicitly called out as friends, close neighbors, or long-term companions.\n"
        "4. Output only the pure raw JSON object complying with the schema. No markdown wrapping, no conversational filler."
    )

    try:
        response = client.chat.complete(
            model="mistral-small-2506",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Extract structured information from this obituary text:\n\n{obituary_text}"
                }
            ],
            # Enforces strict structure validation natively at the API boundary
            response_format={
                "type": "json_object"
            }
        )

        raw_content = response.choices[0].message.content

        # Parse the string into a ready-to-use Python dictionary
        extracted_dict = json.loads(raw_content)
        return extracted_dict, obituary_text

    except json.JSONDecodeError as json_err:
        print(f"❌ Mistral returned malformed JSON payload text string: {json_err}")
        return {}
    except Exception as e:
        print(f"⚠️ Mistral extraction processing failure: {e}")
        return {}


def _pick_best_address_match(target_address: str, candidates: list) -> dict | None:
    """
    Uses LLM to pick which candidate address matches the target,
    handling abbreviation/formatting differences (Rd vs Road, E vs East, etc.)
    """
    if not candidates:
        return None

    # Limit candidates to avoid token issues
    if len(candidates) > 20:
        candidates = candidates[:20]

    candidate_list = "\n".join(
        f"{i + 1}. {c['address_text']}" for i, c in enumerate(candidates)
    )

    prompt = f"""You are matching property addresses that may be formatted differently.

Target address: {target_address}

Candidate addresses:
{candidate_list}

Which candidate number refers to the SAME physical address as the target?
Reply with ONLY a JSON object in this format:
{{"match": <number or 0 if none>, "reason": "<brief reason>"}}

Example: {{"match": 2, "reason": "Same house number and street name"}}"""

    try:
        client = get_mistral_client()
        response = client.chat.complete(
            model="mistral-small-2506",
            messages=[
                {"role": "system", "content": "You are an address matching expert. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        match_num = result.get('match', 0)

        if 1 <= match_num <= len(candidates):
            return candidates[match_num - 1]

    except Exception as e:
        print(f"Address matching error: {e}")
        # Fallback: try to extract number from response
        try:
            raw = response.choices[0].message.content
            match_num = int(re.search(r'\d+', raw).group())
            if 1 <= match_num <= len(candidates):
                return candidates[match_num - 1]
        except:
            pass

    return None


def normalize_case_numbers_with_mistral(case_numbers):
    client = get_mistral_client()

    SYSTEM_PROMPT = """
You are a precise data normalization system for New Jersey foreclosure case numbers.

You will receive a JSON array containing case numbers with indexes.

For EVERY input item:
1. Preserve its index.
2. Normalize the case number.
3. Return exactly one output item for every input item.
4. Never change the index.
5. Never omit an item.
6. Never add an item.

Canonical format:

<prefix>-<docket>-<2-digit-year>

Rules:

- Prefix must be "f" or "ch".
- Prefix is lowercase.
- Preserve ALL docket digits.
- Year must be exactly 2 digits.
- If the input begins with a 2-digit year, that is the year.
- If the input begins with a letter/prefix, the last 2 digits are the year.
- Unknown letter prefixes should normally be treated as "f".
- Remove suffixes such as ALIAS or AKA.
- Remove spaces, underscores, and unnecessary punctuation.
- Do not remove digits.

Examples:

F-008086-25ALIAS -> f-008086-25
F794216 -> f-7942-16
L338714 -> f-3387-14
26000136 -> f-000136-26
F00520925 -> f-005209-25
F-010023-24 -> f-010023-24
26-6654 -> f-6654-26

If a case cannot be confidently normalized, return "INVALID".

Return ONLY valid JSON:

[
    {
        "index": 0,
        "normalized": "f-1234-26"
    }
]
"""

    response = client.chat.complete(
        model="mistral-small-latest",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": json.dumps(case_numbers)
            }
        ],
    )

    content = response.choices[0].message.content.strip()

    content = content.replace("```json", "")
    content = content.replace("```", "")
    content = content.strip()

    results = json.loads(content)

    return results


def extract_financial_obligations(raw_text: str):
    """
    Extract standardized financial obligations from foreclosure text.

    Parameters
    ----------
    raw_text : str
        Raw foreclosure notice.

    client
        OpenAI-compatible client.

    model : str
        Model name.

    Returns
    -------
    dict
    """
    client = get_mistral_client()
    system_prompt = """
You are an expert information extraction engine.

Your ONLY job is to extract financial obligations from NJ sheriff's sale / foreclosure notices.

Return ONLY valid JSON. Do not explain anything.

Use exactly this schema:

{
  "financial_obligations": [
    {
      "category": "unpaid_amount | tax | utility | lien | fee | claim | municipal_charge | advance | other",
      "subtype": "",
      "amount": null,
      "status": "open | paid | billed | due | owed | unknown",
      "due_date": null,
      "period": null,
      "as_of": null,
      "penalty": false,
      "interest": null,
      "exists": null,
      "holder": null,
      "certificate": null,
      "description": null
    }
  ]
}

HOW TO CLASSIFY EACH DOLLAR FIGURE — REASON, DON'T PATTERN-MATCH:

For every dollar amount you find, first ask: "what noun phrase grammatically
describes what this money IS?" Find the words that directly govern the amount
(usually right before or after it), not just words that happen to appear
somewhere in the same sentence or paragraph.

Then classify based on what that governing description says:

-> "unpaid_amount": the figure represents the WHOLE debt/sale being enforced,
as a single summary total. It is described as a price, judgment, payoff, or
"the amount due" for the sale/execution/foreclosure itself — covering the
matter as a whole, not one line-item. There is typically only one (occasionally
two, e.g. a payoff and a judgment) such figure per notice, and it is not tied
to a specific tax period, utility type, or certificate/instrument number.

-> "lien" / "tax" / "utility" / "municipal_charge": the figure is described as
belonging to ONE specific, named basis — a particular tax quarter/date, a
water or sewer bill, a certificate/TSC/CTL/instrument number, or a named
lienholder. Itemized charges keep their specific category and basis even when
the dollar amount is large — the amount itself is never the deciding factor,
only what the text says the money IS for.

-> "advance": money the plaintiff paid after judgment (insurance, inspections,
taxes) that plaintiff seeks reimbursement or priority for.

CRITICAL PITFALL TO AVOID: notices often contain generic disclaimer sentences
that use words like "lien," "encumbrance," or "charges" in a general legal
sense — e.g. boilerplate about liability, priority, or accuracy of information
— WITHOUT actually describing any specific dollar figure. These sentences are
not attached to a number and must never influence how you classify a nearby
total. Before using a word like "lien" as a classification signal, confirm
that word is the grammatical subject actually describing that specific dollar
amount — not just present somewhere nearby in the paragraph.

If you are ever uncertain whether a figure is the whole-sale total or an
itemized charge, prefer "unpaid_amount" only when the figure is described as
covering the sale/execution/judgment as a whole; prefer the itemized category
whenever the text ties the amount to one named tax period, utility, or
certificate/instrument number.

CALIBRATION EXAMPLES (for reasoning pattern, not phrase-matching):

Text: "...property taxes are due and owing in the amount of $3,976.59...
pursuant to TSC #26-00890."
Reasoning: this amount is tied to a specific tax certificate and a specific
tax obligation for a named parcel -> itemized charge.
-> {"category": "tax", "subtype": "quarterly_tax", "amount": 3976.59,
    "certificate": "TSC #26-00890", "status": "owed"}

Text: "...I will expose for sale... The approximate amount due on this
execution is $283,705.98 plus interest, cost, printers' fees, Sheriff's fees
and commission. The prior liens, as per affidavit of consideration are not a
representation of fact on the part of the Sheriff."
Reasoning: "$283,705.98" is directly governed by "the amount due on this
execution" — describing the whole sale/judgment as one total. The word
"liens" appears only in the following disclaimer sentence about the accuracy
of information, which does not describe or attach to this dollar figure at
all -> whole-sale total, not a lien.
-> {"category": "unpaid_amount", "subtype": "amount_due_execution",
    "amount": 283705.98, "status": "due"}

Text: "...THE AMOUNT ADVANCED WAS $10,492.22 AND THE PLAINTIFF HAS OBTAINED
AN ORDER TO BE REIMBURSED..."
Reasoning: described as an advance the plaintiff made and seeks reimbursement
for -> advance, not a lien or unpaid_amount.
-> {"category": "advance", "subtype": "advance_reimbursement", "amount": 10492.22,
    "status": "owed"}

OTHER NORMALIZATION RULES:
- Every distinct monetary figure becomes one object. Preserve every separate amount, including multiple parcels/addresses billed separately.
- If text says "plus penalty", set penalty=true.
- If an explicit interest dollar figure is given, store it in interest.
- If a charge is mentioned but no amount is given, amount=null and exists=true.
- Normalize dates to YYYY-MM-DD when a specific date is given. If only a quarter/year is given, put it in "period" instead and leave due_date/as_of null.

Normalize categories (for tax/utility/lien/fee/claim/municipal_charge subtypes):
Taxes: tax, quarterly_tax, municipal_tax
Utilities: sewer, water, ccmua, combined_utilities
Fees: property_registration, vacant_property
Claims: solar_claim
Liens: tax_lien, utility_lien, third_party_tax_lien

Normalize statuses:
OPEN -> open | PAID -> paid | BILLED -> billed | OWED IN ARREARS -> owed | DUE -> due

If information is missing, return null. Never invent information.
"""
    while True:
        try:
            response = client.chat.complete(
                model="mistral-small-latest",
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": raw_text
                    }
                ]
            )

            return json.loads(response.choices[0].message.content)
        except SDKError:
            time.sleep(1)
            continue
        except Exception as e:
            print(f"Mistral financial obligations failed for {raw_text}: {e}")
            return {"financial_obligations": []}

name_system_prompt = """
You are a name extraction system.

Your ONLY task is to extract the FIRST NAME and LAST NAME of the primary person from the provided name string.

Return ONLY valid JSON in exactly this format:
{
  "first_name": "FirstName",
  "last_name": "LastName"
}

RULES:

1. Extract the first name and last name of the PRIMARY person.
2. Ignore titles:
   - Mr.
   - Mrs.
   - Ms.
   - Miss
   - Dr.
   - Rev.
   - Hon.
   - and similar titles.
3. Ignore middle names and middle initials.
4. Ignore suffixes such as:
   - Jr.
   - Sr.
   - II
   - III
   - IV
   - V
   - Esq.
5. Ignore anything after:
   - A/K/A
   - AKA
   - A.K.A.
   - FKA
   - F/K/A
   - formerly known as
   These indicate an alternate/former name. Use the name BEFORE the indicator.
6. Preserve hyphenated last names completely.
7. Preserve compound last names such as:
   - Van Rye
   - De Ghetto
   - De La Cruz
   - Van Buren
8. Preserve apostrophes in names:
   - O'Shea
   - O'Connor
9. Convert ALL-CAPS names to normal capitalization.
10. If the input contains punctuation around the name, ignore the punctuation.
11. Do not invent or infer missing names.
12. If a first name or last name cannot be determined, return null for that field.
13. Return JSON only. Do not include explanations, markdown, or additional text.

EXAMPLES:

"Mrs. William Wilhite"
-> {"first_name":"William","last_name":"Wilhite"}

"JENNIFER J. JORDAN"
-> {"first_name":"Jennifer","last_name":"Jordan"}

"JOANN VAN RYE"
-> {"first_name":"Joann","last_name":"Van Rye"}

"KENNETH C. VAN RYE"
-> {"first_name":"Kenneth","last_name":"Van Rye"}

"HENRY AYER JR"
-> {"first_name":"Henry","last_name":"Ayer"}

"Leslie Harvard-Taylor"
-> {"first_name":"Leslie","last_name":"Harvard-Taylor"}

"Bernadette Sheridan A/K/A Bernadette Phillips Sheridan"
-> {"first_name":"Bernadette","last_name":"Sheridan"}

"Debra Ann Steventon FKA Debra Ann Kasubinski"
-> {"first_name":"Debra","last_name":"Steventon"}

"RONALD J. MARKOVICH, JR. A/K/A RONALD MARKOVICH"
-> {"first_name":"Ronald","last_name":"Markovich"}

"Roger Deghetto A/K/A Roger De Ghetto"
-> {"first_name":"Roger","last_name":"Deghetto"}

"WILLIAM O`SHEA"
-> {"first_name":"William","last_name":"O'Shea"}
"""

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """
... (your exact system prompt from before, unchanged) ...
"""

@pysnooper.snoop()
def extract_first_last_name_anthropic(name_string: str) -> dict:
    user_prompt = f'Extract the first and last name from this name: "{name_string}"'

    try:
        effective_key = os.getenv("ANTHROPIC_API_KEY")
        if not effective_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

        client = anthropic.Anthropic(api_key=effective_key)
    
        response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=name_system_prompt,  # make sure SYSTEM_PROMPT states: "Return results in the same order as input, one entry per input, no skipping."
        messages=[{"role": "user", "content": user_prompt}],

    )
        content = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        # Defensive: strip markdown fences or stray text around the JSON
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)

        result = json.loads(content)
        return {
            "first_name": result.get("first_name"),
            "last_name": result.get("last_name"),
        }

    except Exception as e:
        traceback.print_exc()
        print(f"Name extraction failed for {name_string}: {e}")
        return {"first_name": None, "last_name": None}

def extract_financial_obligations_ling(raw_text: str):
    """
    Extract standardized financial obligations from foreclosure text.

    Parameters
    ----------
    raw_text : str
        Raw foreclosure notice.

    Returns
    -------
    dict
        {
          "financial_obligations": [
            {
              "category": "...",
              "subtype": "...",
              "amount": ...,
              "status": "...",
              "due_date": "...",
              "period": "...",
              "as_of": "...",
              "penalty": ...,
              "interest": ...,
              "exists": ...,
              "holder": "...",
              "certificate": "...",
              "description": "..."
            }
          ]
        }
    """

    system_prompt = """
You are an expert information extraction engine specializing in
New Jersey sheriff's sale, foreclosure, municipal charge, tax,
utility, lien, and judgment documents.

Your ONLY job is to extract financial obligations from the provided
NJ foreclosure/sheriff's sale text.

Return ONLY valid JSON.
Do not explain anything outside the JSON.
Do not use markdown.
Do not include ```json fences.

Use EXACTLY this schema:

{
  "financial_obligations": [
    {
      "category": "unpaid_amount | tax | utility | lien | fee | claim | municipal_charge | advance | other",
      "subtype": "",
      "amount": null,
      "status": "open | paid | billed | due | owed | unknown",
      "due_date": null,
      "period": null,
      "as_of": null,
      "penalty": false,
      "interest": null,
      "exists": null,
      "holder": null,
      "certificate": null,
      "description": null
    }
  ]
}


==================================================
HOW TO CLASSIFY EACH DOLLAR FIGURE
==================================================

REASON CAREFULLY ABOUT WHAT EACH DOLLAR FIGURE ACTUALLY REPRESENTS.

For every dollar amount you find, first ask:

"What noun phrase grammatically describes what this money IS?"

Identify the words that directly govern or describe the amount,
usually immediately before or after the amount.

Do NOT classify an amount merely because a related word such as
"lien", "tax", "charges", or "encumbrance" appears somewhere nearby
in the same sentence or paragraph.

Classify the amount based on what the text explicitly says the money IS.


--------------------------------------------------
1. unpaid_amount
--------------------------------------------------

Use "unpaid_amount" when the figure represents the WHOLE debt,
sale, execution, judgment, payoff, or foreclosure amount as a
single summary total.

Typical descriptions include:

- "amount due on this execution"
- "amount due"
- "judgment amount"
- "payoff amount"
- "total amount due"
- "amount necessary to satisfy the judgment"
- "amount due for the sale"
- "judgment entered in the amount of..."
- similar language describing the matter as a whole

This amount covers the overall foreclosure/execution/judgment,
rather than one specific line item.

There is typically only one such figure per notice, although
occasionally there may be two, such as a judgment amount and a
separate payoff amount.

An unpaid_amount is NOT tied specifically to:

- a particular tax period
- a particular utility bill
- a tax certificate
- a lien certificate
- a municipal registration charge
- a specific third-party claim

The size of the amount does NOT determine the category.


--------------------------------------------------
2. tax
--------------------------------------------------

Use "tax" when the amount represents a specific tax obligation.

Examples:

- property taxes
- quarterly property taxes
- municipal taxes
- taxes due and owing
- taxes in arrears
- tax balance
- a tax amount associated with a specific parcel or period

If the text identifies a tax certificate or tax certificate number,
the obligation remains a tax and the certificate should be recorded
in the "certificate" field.


--------------------------------------------------
3. utility
--------------------------------------------------

Use "utility" when the amount represents a specific utility obligation.

Examples:

- water
- sewer
- CCMUA
- combined water/sewer
- utility bill
- sewer charges
- water charges

Normalize utility subtypes as:

- "sewer"
- "water"
- "ccmua"
- "combined_utilities"


--------------------------------------------------
4. lien
--------------------------------------------------

Use "lien" when the amount is explicitly associated with a specific
lien or lienholder.

Examples:

- tax lien
- utility lien
- third-party tax lien
- lien amount
- lien claim
- amount owed to a named lienholder

Normalize lien subtypes as:

- "tax_lien"
- "utility_lien"
- "third_party_tax_lien"


--------------------------------------------------
5. municipal_charge
--------------------------------------------------

Use "municipal_charge" when the amount is a specific municipal
charge that does not fit better under tax, utility, lien, or fee.

The amount must actually be associated with the municipal charge.

Do not use generic mentions of municipal charges as evidence for
classifying an unrelated dollar figure.


--------------------------------------------------
6. fee
--------------------------------------------------

Use "fee" for specific fees or registration-related charges.

Normalize known fee subtypes as:

- "property_registration"
- "vacant_property"

Use "fee" for other clearly identified fees when appropriate.


--------------------------------------------------
7. claim
--------------------------------------------------

Use "claim" for a specific financial claim that does not represent
the general foreclosure judgment/debt.

Normalize known claim subtypes as:

- "solar_claim"


--------------------------------------------------
8. advance
--------------------------------------------------

Use "advance" when the plaintiff or another party paid money after
judgment and is seeking reimbursement, repayment, or priority for
that amount.

Common examples:

- insurance advances
- tax advances
- inspection advances
- preservation advances
- other plaintiff advances

If the text says something similar to:

"THE AMOUNT ADVANCED WAS $10,492.22 AND THE PLAINTIFF HAS OBTAINED
AN ORDER TO BE REIMBURSED..."

classify the amount as:

{
  "category": "advance",
  "subtype": "advance_reimbursement",
  "amount": 10492.22,
  "status": "owed"
}


==================================================
CRITICAL PITFALL: GENERIC LEGAL DISCLAIMER LANGUAGE
==================================================

Foreclosure notices frequently contain generic disclaimer sentences
using words such as:

- lien
- liens
- encumbrance
- charges
- taxes
- claims
- obligations

These words may appear in boilerplate language about liability,
priority, accuracy of information, or legal rights.

Such language MUST NOT influence the classification of a nearby
dollar amount unless the word actually describes that specific
dollar amount.

Before using a word such as "lien" as a classification signal,
confirm that the lien is actually the grammatical subject or
description governing that specific amount.

Do NOT classify a total as a lien simply because the word "lien"
appears somewhere nearby.

Likewise, do not classify an amount as a tax, utility, fee, or
municipal charge merely because those words occur elsewhere in
the paragraph.

The relationship between the amount and its description is what
determines the category.


==================================================
WHOLE-SALE TOTAL VS ITEMIZED CHARGE
==================================================

If you are uncertain whether a figure is the whole-sale total or
an itemized charge:

Use "unpaid_amount" ONLY when the figure is described as covering
the sale, execution, judgment, payoff, or foreclosure as a whole.

Use the specific itemized category whenever the text ties the
amount to:

- one named tax period
- one tax obligation
- one utility
- one certificate
- one instrument number
- one municipal charge
- one lienholder
- one specific claim
- one specific fee
- one advance


==================================================
CALIBRATION EXAMPLES
==================================================

These examples demonstrate the REASONING PATTERN.
Do NOT simply pattern-match phrases.


EXAMPLE 1:

Text:

"...property taxes are due and owing in the amount of $3,976.59...
pursuant to TSC #26-00890."

Reasoning:

The amount is tied to a specific tax obligation and a specific
tax certificate for the parcel. Therefore it is an itemized tax
charge, not the overall foreclosure amount.

Output:

{
  "category": "tax",
  "subtype": "quarterly_tax",
  "amount": 3976.59,
  "certificate": "TSC #26-00890",
  "status": "owed"
}


EXAMPLE 2:

Text:

"...I will expose for sale... The approximate amount due on this
execution is $283,705.98 plus interest, cost, printers' fees,
Sheriff's fees and commission. The prior liens, as per affidavit
of consideration are not a representation of fact on the part
of the Sheriff."

Reasoning:

"$283,705.98" is directly governed by "the amount due on this
execution", which describes the whole sale/judgment amount.

The word "liens" occurs only in the following disclaimer sentence
about the accuracy of information. It does NOT describe the
$283,705.98 figure.

Therefore this is the whole-sale/execution amount.

Output:

{
  "category": "unpaid_amount",
  "subtype": "amount_due_execution",
  "amount": 283705.98,
  "status": "due"
}


EXAMPLE 3:

Text:

"...THE AMOUNT ADVANCED WAS $10,492.22 AND THE PLAINTIFF HAS
OBTAINED AN ORDER TO BE REIMBURSED..."

Reasoning:

The amount is explicitly described as an advance made by the
plaintiff and sought for reimbursement.

Output:

{
  "category": "advance",
  "subtype": "advance_reimbursement",
  "amount": 10492.22,
  "status": "owed"
}


==================================================
OTHER EXTRACTION AND NORMALIZATION RULES
==================================================

1. EVERY DISTINCT MONETARY FIGURE

Every distinct monetary figure becomes ONE financial obligation
object.

Preserve every separate amount.

If multiple parcels, properties, taxes, utilities, liens, or
addresses have separately stated amounts, create separate objects.

Do NOT combine separate dollar figures into one object unless the
text explicitly presents them as one single total.


2. AMOUNTS

Extract monetary amounts as numbers.

Examples:

"$3,976.59" -> 3976.59
"$283,705.98" -> 283705.98
"$10,492.22" -> 10492.22

Do not include the "$" symbol in the amount field.


3. PENALTY

If the text explicitly states that a charge has a penalty or is
subject to a penalty, set:

"penalty": true

Otherwise:

"penalty": false

Do not set penalty=true merely because interest or late charges
are mentioned.


4. INTEREST

If an explicit interest DOLLAR AMOUNT is given, store that numeric
amount in the "interest" field.

Example:

"interest of $1,250.00"

->

"interest": 1250.00

If interest is mentioned but there is no explicit dollar amount,
leave:

"interest": null


5. CHARGES WITH NO AMOUNT

If a specific financial obligation is clearly mentioned but no
amount is provided:

"amount": null
"exists": true

Example:

"Outstanding sewer charges remain due."

->

{
  "category": "utility",
  "subtype": "sewer",
  "amount": null,
  "exists": true
}

Do NOT create an obligation merely because a generic legal term
appears.


6. DATES

Normalize specific dates to:

YYYY-MM-DD

Example:

"March 15, 2025"
-> "2025-03-15"

If only a quarter/year or period is given, put that information
in "period" instead.

Example:

"2025 Q3 taxes"

->

"period": "2025 Q3"

and:

"due_date": null
"as_of": null

Do not invent an exact date from a quarter or year.


7. as_of

Use "as_of" when the document explicitly states the date on which
the amount/balance was calculated or reported.

Normalize it to YYYY-MM-DD when it is a specific date.

Do not confuse "as of" dates with due dates.


8. due_date

Use "due_date" only when the text explicitly identifies a due date
for that obligation.

Do not infer a due date from the date of the notice.


9. STATUS NORMALIZATION

Normalize statuses as follows:

OPEN -> "open"
PAID -> "paid"
BILLED -> "billed"
OWED / OWED IN ARREARS -> "owed"
DUE -> "due"

If the status cannot be determined:

"status": "unknown"


10. CATEGORY NORMALIZATION

Use exactly these top-level categories:

"unpaid_amount"
"tax"
"utility"
"lien"
"fee"
"claim"
"municipal_charge"
"advance"
"other"


11. SUBTYPE NORMALIZATION

Known tax subtypes:

- "tax"
- "quarterly_tax"
- "municipal_tax"

Known utility subtypes:

- "sewer"
- "water"
- "ccmua"
- "combined_utilities"

Known fee subtypes:

- "property_registration"
- "vacant_property"

Known claim subtypes:

- "solar_claim"

Known lien subtypes:

- "tax_lien"
- "utility_lien"
- "third_party_tax_lien"

For unpaid amounts, use a descriptive subtype such as:

- "amount_due_execution"
- "judgment_amount"
- "payoff_amount"
- "total_amount_due"

Only use a subtype when supported by the text.


12. HOLDER

If the text explicitly identifies the holder, claimant, lienholder,
municipality, utility, plaintiff, or other entity associated with
the specific obligation, put that entity in "holder".

Do not invent a holder.

If unknown:

"holder": null


13. CERTIFICATE

If a specific certificate, TSC, CTL, tax certificate, or other
instrument number is explicitly associated with the obligation,
store it in "certificate".

Example:

"TSC #26-00890"

->

"certificate": "TSC #26-00890"

Do not put unrelated certificate numbers into this field.


14. DESCRIPTION

Use "description" for a concise description of the specific
financial obligation when useful.

The description should summarize what the amount represents.

Do not copy large portions of the source text.

If no useful description is available:

"description": null


15. MISSING INFORMATION

If information is missing:

- amount -> null
- due_date -> null
- period -> null
- as_of -> null
- interest -> null
- holder -> null
- certificate -> null
- description -> null

Never invent information.


==================================================
FINAL VALIDATION BEFORE RETURNING JSON
==================================================

Before returning the result, verify:

1. Every monetary figure that represents a distinct obligation
   has been captured.

2. Separate monetary figures have not been incorrectly combined.

3. A whole-sale execution/judgment amount has not been classified
   as a lien, tax, utility, or municipal charge merely because
   those words appear nearby.

4. Itemized charges remain itemized even when their amounts are large.

5. Street/property information is irrelevant to financial
   classification unless it identifies which obligation belongs
   to which parcel.

6. Every best-match classification is based on the words that
   actually describe the specific amount.

7. No information has been invented.

8. The output is valid JSON and contains ONLY the
   "financial_obligations" object.

Return JSON ONLY.
"""

    while True:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                    "Content-Type": "application/json",
                },
                data=json.dumps({
                    "model": "inclusionai/ling-3.0-flash-sante:free",
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": raw_text
                        }
                    ],
                    "temperature": 0,
                    "reasoning": {
                        "enabled": False
                    },
                    "response_format": {
                        "type": "json_object"
                    }
                }),
                timeout=120
            )

            response.raise_for_status()

            result = response.json()

            content = result["choices"][0]["message"]["content"]

            return json.loads(content)

        except requests.RequestException as e:
            print(f"OpenRouter financial obligations request failed: {e}")
            time.sleep(1)
            continue

        except json.JSONDecodeError as e:
            print(f"Ling returned invalid JSON: {e}")
            return {
                "financial_obligations": []
            }

        except Exception as e:
            print(f"Ling financial obligations failed: {e}")
            return {
                "financial_obligations": []
            }

def match_property_address(target_address: str, candidate_addresses: list):
    """
    Uses Mistral to decide which candidate address (scraped from a county
    sheriff sale listing table) matches the target property address.

    Parameters
    ----------
    target_address : str
        The address we're trying to find (e.g. from the case record).

    candidate_addresses : list[dict]
        List of {"index": int, "address": str} scraped from listing rows.

    Returns
    -------
    dict
        {
          "best_match_index": int | null,
          "matched_address": str | null,
          "confidence": "high" | "medium" | "low" | "none",
          "reasoning": str | null
        }
    """
    client = get_mistral_client()

    system_prompt = """
You are an expert address matching engine.

Your ONLY job is to decide which candidate address, if any, refers to the
same physical property as the target address.

Return ONLY valid JSON. Do not explain anything outside the JSON.

Use exactly this schema:

{
  "best_match_index": null,
  "matched_address": null,
  "confidence": "high | medium | low | none",
  "reasoning": null
}

Rules:

- Addresses may differ in formatting but still refer to the same property:
  - Abbreviations: St/Street, Ave/Avenue, Rd/Road, Dr/Drive, Blvd/Boulevard,
    N/North, S/South, E/East, W/West, Apt/Unit/#
  - Minor typos or OCR noise (e.g. "1O5" vs "105")
  - Extra/missing unit, apartment, or suite numbers
  - Different word order (e.g. "123 Main St" vs "Main St 123")
  - Presence or absence of city/state/zip in one of the two strings
- The house/street NUMBER must match exactly. Never match two addresses
  with different street numbers, even if the street name is similar.
- The street NAME must be the same or a clear abbreviation/typo variant.
  Do not match different street names just because they sound similar.
- If multiple candidates could plausibly match, pick the closest one and
  lower the confidence to "medium" or "low" accordingly.
- If no candidate plausibly matches, set best_match_index=null,
  matched_address=null, confidence="none".
- Never invent or guess an address that is not in the candidate list.
- confidence="high" only when you are certain it's the same property.
"""

    user_content = json.dumps({
        "target_address": target_address,
        "candidates": candidate_addresses
    })

    while True:
        try:
            response = client.chat.complete(
                model="mistral-small-latest",
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
            )
            return json.loads(response.choices[0].message.content)
        except SDKError:
            time.sleep(1)
            continue
        except Exception as e:
            print(f"Mistral address match failed for '{target_address}': {e}")
            return {
                "best_match_index": None,
                "matched_address": None,
                "confidence": "none",
                "reasoning": f"error: {e}"
            }

import requests


def extract_first_last_name_groq(name):
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
        {
            "role": "system",
            "content": "You are a name extraction system.\n\nYour ONLY task is to extract the FIRST NAME and LAST NAME of the primary person from the provided name string.\n\nReturn ONLY valid JSON in exactly this format:\n{\n  \"first_name\": \"FirstName\",\n  \"last_name\": \"LastName\"\n}\n\nRULES:\n\n1. Extract the first name and last name of the PRIMARY person.\n2. Ignore titles:\n   - Mr.\n   - Mrs.\n   - Ms.\n   - Miss\n   - Dr.\n   - Rev.\n   - Hon.\n   - and similar titles.\n3. Ignore middle names and middle initials.\n4. Ignore suffixes such as:\n   - Jr.\n   - Sr.\n   - II\n   - III\n   - IV\n   - V\n   - Esq.\n5. Ignore anything after:\n   - A/K/A\n   - AKA\n   - A.K.A.\n   - FKA\n   - F/K/A\n   - formerly known as\n   These indicate an alternate/former name. Use the name BEFORE the indicator.\n6. Preserve hyphenated last names completely.\n7. Preserve compound last names such as:\n   - Van Rye\n   - De Ghetto\n   - De La Cruz\n   - Van Buren\n8. Preserve apostrophes in names:\n   - O'Shea\n   - O'Connor\n9. Convert ALL-CAPS names to normal capitalization.\n10. If the input contains punctuation around the name, ignore the punctuation.\n11. Do not invent or infer missing names.\n12. If a first name or last name cannot be determined, return null for that field.\n13. Return JSON only. Do not include explanations, markdown, or additional text.\n\nEXAMPLES:\n\n\"Mrs. William Wilhite\"\n-> {\"first_name\":\"William\",\"last_name\":\"Wilhite\"}\n\n\"JENNIFER J. JORDAN\"\n-> {\"first_name\":\"Jennifer\",\"last_name\":\"Jordan\"}\n\n\"JOANN VAN RYE\"\n-> {\"first_name\":\"Joann\",\"last_name\":\"Van Rye\"}\n\n\"KENNETH C. VAN RYE\"\n-> {\"first_name\":\"Kenneth\",\"last_name\":\"Van Rye\"}\n\n\"HENRY AYER JR\"\n-> {\"first_name\":\"Henry\",\"last_name\":\"Ayer\"}\n\n\"Leslie Harvard-Taylor\"\n-> {\"first_name\":\"Leslie\",\"last_name\":\"Harvard-Taylor\"}\n\n\"Bernadette Sheridan A/K/A Bernadette Phillips Sheridan\"\n-> {\"first_name\":\"Bernadette\",\"last_name\":\"Sheridan\"}\n\n\"Debra Ann Steventon FKA Debra Ann Kasubinski\"\n-> {\"first_name\":\"Debra\",\"last_name\":\"Steventon\"}\n\n\"RONALD J. MARKOVICH, JR. A/K/A RONALD MARKOVICH\"\n-> {\"first_name\":\"Ronald\",\"last_name\":\"Markovich\"}\n\n\"Roger Deghetto A/K/A Roger De Ghetto\"\n-> {\"first_name\":\"Roger\",\"last_name\":\"Deghetto\"}\n\n\"WILLIAM O`SHEA\"\n-> {\"first_name\":\"William\",\"last_name\":\"O'Shea\"}"
        },
        {
            "role": "user",
            "content": "Extract the first and last name from this name: " + name
        }
        ],
        temperature=1,
        top_p=1,
        reasoning_effort="medium",
        stream=False,
        stop=None
    )
    
    response_text = completion.choices[0].message.content
    
    try:
        result = json.loads(response_text)
        return result  # Returns tuple
    except (json.JSONDecodeError, KeyError):
        return None


def match_property_address_groq(target_address: str, candidate_addresses: list):
    """
    Uses Groq to decide which candidate address,
    if any, refers to the same physical property as the target address.

    Parameters
    ----------
    target_address : str
        The address we're trying to find.

    candidate_addresses : list[dict]
        List of {"index": int, "address": str} scraped from listing rows.

    Returns
    -------
    dict
        {
          "best_match_index": int | null,
          "matched_address": str | null,
          "confidence": "high" | "medium" | "low" | "none",
          "reasoning": str | null
        }
    """

    system_prompt = """
You are an expert property address matching engine.

Your ONLY task is to determine whether one of the candidate addresses refers
to the SAME PHYSICAL PROPERTY as the target address.

Return ONLY valid JSON using exactly this structure:

{
  "best_match_index": null,
  "matched_address": null,
  "confidence": "high",
  "reasoning": null
}

IMPORTANT MATCHING RULES:

1. STREET NUMBER IS A HARD REQUIREMENT
- The primary street/house number must match.
- NEVER match addresses with different street numbers.
- Example:
  "105 Main Street" MUST NOT match "106 Main Street".
- Do not treat similar numbers as matches.
- Minor OCR errors may be corrected only when the intended number is obvious,
  such as "1O5" being OCR for "105".

2. STREET NAME MUST MATCH
- The street name must be the same or an obvious formatting/OCR variant.
- Accept common abbreviations:
  St = Street
  Ave = Avenue
  Rd = Road
  Dr = Drive
  Blvd = Boulevard
  Ln = Lane
  Ct = Court
  Pl = Place
  Pkwy = Parkway
  Hwy = Highway
- Accept directional abbreviations:
  N = North
  S = South
  E = East
  W = West
  NE = Northeast
  NW = Northwest
  SE = Southeast
  SW = Southwest
- Do NOT match different street names merely because they sound similar.

3. ADDRESS FORMATTING
These differences are acceptable when the underlying property is clearly
the same:
- "123 Main St" vs "123 Main Street"
- "123 N Main St" vs "123 North Main Street"
- Different capitalization
- Different punctuation
- Extra spaces
- Different word ordering
- City/state/ZIP present in one address but missing from the other
- "Apt", "Apartment", "Unit", "#", "Suite" formatting differences

4. UNIT / APARTMENT NUMBERS
- If both addresses contain a unit/apartment/suite number, it should match.
- Do NOT automatically treat different unit numbers as the same property.
- If one address contains a unit number and the other does not, the match
  may still be valid if the street address clearly identifies the same
  property.
- Lower confidence when the missing unit number creates uncertainty.

5. CITY / STATE / ZIP
- City, state, and ZIP are supporting evidence.
- Their absence from one address does NOT automatically prevent a match.
- If they conflict with the target address, lower confidence or reject the
  candidate depending on how significant the conflict is.
- Do not match an address in a clearly different location simply because
  the street name and number are identical.

6. OCR / SCRAPED DATA ERRORS
The candidate addresses may come from OCR or web scraping and may contain
minor errors.
Accept obvious OCR mistakes when the intended address is unambiguous.

Examples:
"O" vs "0"
"I" vs "1"
missing punctuation
duplicated spaces
minor character errors

Do NOT make aggressive corrections or invent missing information.

7. MULTIPLE CANDIDATES
- If multiple candidates plausibly refer to the same property, select the
  strongest match.
- Prefer candidates with matching street number + street name + city/state.
- Lower confidence if multiple candidates are genuinely ambiguous.

8. NO MATCH
If none of the candidates plausibly refers to the same physical property:

{
  "best_match_index": null,
  "matched_address": null,
  "confidence": "none",
  "reasoning": "No candidate matches the target property address."
}

9. NEVER INVENT DATA
- best_match_index MUST come from the provided candidate list.
- matched_address MUST be copied from the selected candidate.
- Never create or modify an address.
- Never return an index that does not exist in the candidate list.

CONFIDENCE LEVELS:

"high":
The street number and street name clearly match and there are no meaningful
conflicts. City/state/ZIP may also support the match.

"medium":
The property is probably the same, but there is some minor uncertainty,
such as missing city information, OCR noise, or a missing unit number.

"low":
There is substantial uncertainty, but one candidate is still more plausible
than the alternatives.

"none":
No candidate plausibly matches the target address.

The "reasoning" field should be a SHORT explanation of the evidence used.
Do not provide lengthy analysis.

Return JSON ONLY. Do not include markdown or any text outside the JSON object.
"""

    user_content = json.dumps({
        "target_address": target_address,
        "candidates": candidate_addresses
    })

    # Initialize Groq client
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",  # You can also use "llama3-70b-8192" or "gemma2-9b-it"
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                temperature=0,
                top_p=1,
                stream=False,
                stop=None
            )

            # Extract the response content
            content = completion.choices[0].message.content

            # Parse JSON response
            result = json.loads(content)
            
            # Validate the result has expected fields
            required_fields = ["best_match_index", "matched_address", "confidence", "reasoning"]
            if all(field in result for field in required_fields):
                return result
            else:
                raise ValueError("Missing required fields in response")

        except Exception as e:
            print(f"Groq address match failed for '{target_address}' (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                return {
                    "best_match_index": None,
                    "matched_address": None,
                    "confidence": "none",
                    "reasoning": f"error after {max_retries} attempts: {e}"
                }



###################################################
"""
Optimized version of get_bankruptcy_case_status_haiku.

Changes vs. original, in order of impact:
  1. Prompt caching on the instruction block (cache_control) — ~90% cheaper
     on every call after the first, since the ~700-token instructions are
     identical every time and only the document text changes.
  2. Header/footer stripping in pdf_to_text() — removes repeated PACER-style
     boilerplate ("Case X Doc Y Filed Z Page N of M") that adds tokens with
     zero information value.
  3. A separate batch-mode function (submit_bankruptcy_batch /
     retrieve_bankruptcy_batch) for when you don't need real-time results —
     flat 50% off input+output, stacks with caching.

Nothing here changes the instructions themselves, so accuracy should be
unaffected. Test the header-stripping regex against a sample of your real
PDFs before trusting it in production — PACER footer formats vary.
"""

MODEL = "claude-haiku-4-5-20251001"



# ---------------------------------------------------------------------------
# 2. Shared prompt pieces (unchanged content, just split so the static part
#    can be cached)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a legal document analyst specializing in bankruptcy and "
    "foreclosure proceedings. Return only valid JSON."
)

INSTRUCTIONS_BLOCK = """Legal document analyst: NJ foreclosure/bankruptcy proceedings.

TASK: from the document below, determine bankruptcy_case_status and foreclosure_permitted.

bankruptcy_case_status:
- "accepted": case is active/pending, NOT dismissed. Signals: notice of filing, certification of bankruptcy with no dismissal, PACER "Date Closed" blank.
- "denied": case was dismissed, denied, or closed without discharge. Signals: order dismissing petition, order denying confirmation, pre-confirmation dismissal, PACER "Date Closed" with a date, "was dismissed" language.

foreclosure_permitted:
- "yes": case denied/dismissed/closed, OR relief from the automatic stay was granted for this specific property (even if the case itself remains open).
- "no": case is accepted/open AND no relief from stay has been granted — stay still blocks action.

RULES (do not violate):
1. "Order Granting Relief from the Automatic Stay" ≠ case denied. Stay is lifted only for the named property; case stays accepted/open. → status="accepted", foreclosure="yes".
2. "Certification of Bankruptcy Discharge" (or similar title) is not itself proof of denial — read the body; it may instead certify relief from stay.
3. A prior closed case (e.g. from 2004) does not affect the current case's status. Focus only on the current case.
4. "Order to Show Cause Why Case Should Not Be Dismissed" is NOT a dismissal. Case remains accepted/open until an actual dismissal order is entered.

OUTPUT: valid JSON only, no text outside it. Keys:
- bankruptcy_case_status: "accepted" | "denied"
- foreclosure_permitted: "yes" | "no"
- basis: short phrase, e.g. "relief from stay granted", "case dismissed", "stay still in effect"
- justification: 1 sentence citing the specific document language
- case_number: string or null
- relevant_date: dismissal/discharge/stay-relief date, or null
- confidence: 0-100

DOCUMENT:
"""

REQUIRED_FIELDS = [
    "bankruptcy_case_status",
    "foreclosure_permitted",
    "basis",
    "justification",
    "case_number",
    "relevant_date",
    "confidence",
]


def _parse_json_response(content: str) -> dict:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return json.loads(content.strip())


def _error_result(basis: str, justification: str) -> dict:
    return {
        "bankruptcy_case_status": "unknown",
        "foreclosure_permitted": "unknown",
        "basis": basis,
        "justification": justification,
        "case_number": None,
        "relevant_date": None,
        "confidence": 0,
    }


# ---------------------------------------------------------------------------
# 3. Real-time version with prompt caching
# ---------------------------------------------------------------------------

def get_bankruptcy_case_status_haiku(bankruptcy_path):
    """Same behavior as the original function, but:
      - instructions are marked with cache_control so repeated calls only
        pay full price for the instructions block once (then ~10% of that
        cost on every subsequent call, for ~1 hour cache lifetime by default
        -- use cache_control ttl if you need it to persist longer),
      - the document text is cleaned of repeated PACER boilerplate first.

    `client` is passed in rather than constructed here — reuse one client
    across all calls instead of creating a new one per document; it's cheap
    but there's no reason to pay even that overhead 1,000 times.
    """
    client = anthropic.Anthropic(
        api_key=os.getenv("SUPABASE_URL")
    )
    bankruptcy_text = pdf_to_text(bankruptcy_path) 

    max_retries = 3
    retry_delay = 1
    content = ""

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": INSTRUCTIONS_BLOCK,
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": bankruptcy_text,
                            },
                        ],
                    }
                ],
            )
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens
            
            print(f"📊 Token usage:")
            print(f"   Input tokens: {input_tokens}")
            print(f"   Output tokens: {output_tokens}")
            print(f"   Total tokens: {total_tokens}")
            
            # Estimate cost (Haiku pricing: ~$0.25/1M input, ~$1.25/1M output)
            input_cost = (input_tokens / 1_000_000) * 0.25
            output_cost = (output_tokens / 1_000_000) * 1.25
            print(f"   Estimated cost: ${input_cost + output_cost:.6f}")
            content = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

            result = _parse_json_response(content)

            if all(field in result for field in REQUIRED_FIELDS):
                return result
            missing = [f for f in REQUIRED_FIELDS if f not in result]
            raise ValueError(f"Missing required fields: {missing}")

        except anthropic.APIError as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return _error_result(
                    f"Error after {max_retries} attempts: {e}",
                    "Failed to analyze document due to API error.",
                )

        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}\nRaw response: {content[:200]}...")
            return _error_result(
                "Failed to parse JSON response",
                "The model did not return valid JSON.",
            )

        except Exception as e:  # noqa: BLE001
            print(f"Unexpected error: {e}")
            return _error_result(f"Error: {e}", "An unexpected error occurred.")


# ---------------------------------------------------------------------------
# 4. Batch-mode version — use this for overnight / non-urgent runs of many
#    documents. Flat 50% off both input and output tokens, stacks with the
#    caching above. Results typically ready within minutes to a few hours.
# ---------------------------------------------------------------------------

def submit_bankruptcy_batch(bankruptcy_paths: list[str], client: anthropic.Anthropic) -> str:
    """Submit many documents as one batch job. Returns the batch id.

    bankruptcy_paths: list of PDF paths. The custom_id lets you map results
    back to the original path when you retrieve them.
    """
    requests = []
    for i, path in enumerate(bankruptcy_paths):
        bankruptcy_text = pdf_to_text(path)  # noqa: F821
        requests.append(
            {
                "custom_id": f"doc-{i}",
                "params": {
                    "model": MODEL,
                    "max_tokens": 4096,
                    "temperature": 0,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": INSTRUCTIONS_BLOCK,
                                    "cache_control": {"type": "ephemeral"},
                                },
                                {"type": "text", "text": bankruptcy_text},
                            ],
                        }
                    ],
                },
            }
        )

    batch = client.messages.batches.create(requests=requests)
    return batch.id


def retrieve_bankruptcy_batch(batch_id: str, client: anthropic.Anthropic) -> dict:
    """Poll a batch job and return {custom_id: parsed_result} once complete.

    Call this later (e.g. a scheduled job) rather than blocking — batches
    aren't instant. Check client.messages.batches.retrieve(batch_id).processing_status
    if you want to check progress without pulling full results yet.
    """
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        return {"status": batch.processing_status, "results": {}}

    results = {}
    for entry in client.messages.batches.results(batch_id):
        custom_id = entry.custom_id
        if entry.result.type != "succeeded":
            results[custom_id] = _error_result(
                f"Batch item failed: {entry.result.type}",
                "This document failed in the batch job; consider re-running it individually.",
            )
            continue

        message = entry.result.message
        content = "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()
        try:
            parsed = _parse_json_response(content)
            if all(field in parsed for field in REQUIRED_FIELDS):
                results[custom_id] = parsed
            else:
                missing = [f for f in REQUIRED_FIELDS if f not in parsed]
                results[custom_id] = _error_result(
                    f"Missing required fields: {missing}", content[:200]
                )
        except json.JSONDecodeError:
            results[custom_id] = _error_result(
                "Failed to parse JSON response", content[:200]
            )

    return {"status": "ended", "results": results}



"""
match_address_with_haiku -- migrated from Mistral (mistral-large-latest) to
Claude Haiku 4.5.
 
Why this one's different from the document-extraction functions:
  - The prompt is small (~150-300 tokens depending on candidate count), so
    per-call token trimming saves fractions of a cent -- not worth chasing
    hard here.
  - No prompt caching: the candidate list changes every call, so there's
    barely a stable prefix to cache, and even the static instructions text
    (~120 tokens) is nowhere near Haiku 4.5's 4,096-token minimum.
  - Forced tool-use mainly buys reliability here (guaranteed schema, no
    JSONDecodeError path) since the output was already minimal.
 
The one real lever at this scale: memoization. If the same
(target_address, candidate set) pair ever gets re-matched -- retries,
pipeline reruns, re-scraped listings -- skip the API call and return the
cached result. Kept as a plain dict below; swap for a file/DB if you need
it to persist across runs.
"""
 
MODEL = "claude-haiku-4-5-20251001"
 
SYSTEM_PROMPT = (
    "You are matching property addresses for foreclosure sale records. "
    "Use only the information given -- do not assume facts not present."
)
 
INSTRUCTIONS_TEMPLATE = """You are matching a target property address against addresses scraped from a county sheriff sale website. Scraped addresses may differ in formatting: abbreviations (St/Street, Ave/Avenue), extra unit/apt numbers, minor typos, or different word order.
 
Target address: "{target_address}"
 
Candidate addresses:
{numbered_list}
 
Decide which candidate (if any) refers to the same property as the target address."""
 
TOOL_NAME = "record_address_match"
MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "best_match_index": {
            "type": "integer",
            "description": "Index of the best-matching candidate, or -1 if none plausibly match.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
    },
    "required": ["best_match_index", "confidence"],
}
 
_match_cache = {}  # swap for a persistent store if you need it across runs
 
 
def _match_cache_key(target_address: str, candidates: list[dict]) -> str:
    normalized = sorted((c["index"], c["address"]) for c in candidates)
    raw = target_address.strip().lower() + "|" + json.dumps(normalized)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
 
 

MAX_ATTEMPTS=3

@pysnooper.snoop()
def match_address_with_haiku(target_address, candidates):
    """
    Picks which candidate address best matches the target address.
    Uses the service/model configured for the 'salesweb' task in the GUI.
    Falls back to Anthropic claude-haiku-4-5-20251001 if not configured.

    Returns the tool input dict on a successful match, or None on failure.
    """
    # ── Read GUI-configured settings for 'salesweb' ──────────────────────────
    try:
        from app import _settings
    except ImportError:
        _settings = {}
    sw_cfg = (_settings.get("llm_configs") or {}).get("salesweb", {})
    svc   = (sw_cfg.get("service") or "anthropic").lower().strip()
    mdl   = sw_cfg.get("model") or MODEL
    key   = sw_cfg.get("api_key") or os.getenv("SUPABASE_URL")

    if not candidates:
        return None

    cache_key = _match_cache_key(target_address, candidates)
    if cache_key in _match_cache:
        return _match_cache[cache_key]

    numbered_list = "\n".join(
        f"{c['index']}: {c['address']}" for c in candidates
    )
    prompt = INSTRUCTIONS_TEMPLATE.format(
        target_address=target_address,
        numbered_list=numbered_list,
    )

    last_error = None

    # ── Anthropic path: use tool-use for guaranteed structured output ─────────
    if svc == "anthropic":
        client = anthropic.Anthropic(api_key=key)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = client.messages.create(
                    model=mdl,
                    max_tokens=100,
                    temperature=0,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[
                        {
                            "name": TOOL_NAME,
                            "description": "Record the address match decision.",
                            "input_schema": MATCH_SCHEMA,
                        }
                    ],
                    tool_choice={"type": "tool", "name": TOOL_NAME},
                )

                tool_use = next(
                    (b for b in response.content if b.type == "tool_use"),
                    None,
                )

                if tool_use is None:
                    raise ValueError("Model did not return a tool_use block")

                tool_input = tool_use.input
                _match_cache[cache_key] = tool_input
                return tool_input

            except (anthropic.APIError, ValueError, KeyError) as e:
                last_error = e
                print(f"Address match attempt {attempt}/{MAX_ATTEMPTS} failed: {e}")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(2)

        print(f"Address match failed after {MAX_ATTEMPTS} attempts: {last_error}")
        return None

    # ── Non-Anthropic path: call_unified_llm with JSON schema prompt ──────────
    json_schema = {
        "type": "object",
        "properties": {
            "best_match_index": {"type": "integer"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reasoning": {"type": "string"}
        },
        "required": ["best_match_index", "confidence"]
    }
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = call_unified_llm(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                response_json=True,
                service=svc,
                api_key=key,
                model=mdl,
                schema=json_schema,
                task="salesweb",
                max_retries=1,
            )
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict) and "best_match_index" in parsed:
                _match_cache[cache_key] = parsed
                return parsed
            raise ValueError(f"Unexpected response shape: {parsed}")
        except Exception as e:
            last_error = e
            print(f"Address match attempt {attempt}/{MAX_ATTEMPTS} failed ({svc}): {e}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(2)

    print(f"Address match failed after {MAX_ATTEMPTS} attempts: {last_error}")
    return None

TOOL_NAME = "record_normalized_case_numbers"
NORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["results"],
}
 
_norm_cache = {}  # raw case number (stripped/uppercased) -> normalized string
 
 
def _cache_key(raw: str) -> str:
    return raw.strip().upper()
 
 
# Case numbers in this dataset are expected to run from 2015 through 2026.
# Used as a sanity check: if the digit split produces a year outside this
# range, the split is probably wrong (or the input is a genuine edge case)
# -- fall through to Haiku rather than trust a guess.
MIN_VALID_YEAR = 14  # widened from 15 so it doesn't reject "L338714" -> year 14,
                      # which was one of the original confirmed examples. Tighten
                      # back to 15 if 14 was never actually a valid year in your data.
MAX_VALID_YEAR = 26
 
 
def normalize_case_number_regex(case_number: str):
    """Deterministic normalizer. Returns the canonical string, or None if
    this input doesn't confidently match the expected structure (in which
    case it should go to the Haiku fallback, not be guessed)."""
    s = case_number.strip().upper()
    s = re.sub(r"(ALIAS|AKA)", "", s)
    m = re.match(r"^([A-Za-z]+)", s)
    prefix_raw = m.group(1) if m else None
    rest = s[len(prefix_raw):] if prefix_raw else s
    digits = re.sub(r"\D", "", rest)
 
    if len(digits) < 3:
        return None  # not enough digits to split into docket + year
 
    if prefix_raw:
        prefix = "ch" if prefix_raw.lower() == "ch" else "f"
        year, docket = digits[-2:], digits[:-2]
    else:
        prefix = "f"
        year, docket = digits[:2], digits[2:]
 
    if not docket or len(year) != 2 or len(docket) > 8:
        return None  # looks malformed -- let the model judge instead of guessing
 
    if not (MIN_VALID_YEAR <= int(year) <= MAX_VALID_YEAR):
        return None  # year out of plausible range -- likely a bad split, defer to Haiku
 
    return f"{prefix}-{docket}-{year}"
 
 
def _normalize_via_haiku(client: anthropic.Anthropic, case_numbers: list[str]) -> list[str]:
    if not case_numbers:
        return []

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0,
        system=SYSTEM_PROMPT,  # make sure SYSTEM_PROMPT states: "Return results in the same order as input, one entry per input, no skipping."
        messages=[{"role": "user", "content": json.dumps(case_numbers)}],
        tools=[
            {
                "name": TOOL_NAME,
                "description": "Record the normalized case numbers, in input order.",
                "input_schema": NORMALIZE_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    total_tokens = input_tokens + output_tokens

    print(f"📊 Token usage:")
    print(f"   Input tokens: {input_tokens}")
    print(f"   Output tokens: {output_tokens}")
    print(f"   Total tokens: {total_tokens}")

    input_cost = (input_tokens / 1_000_000) * 0.25
    output_cost = (output_tokens / 1_000_000) * 1.25
    print(f"   Estimated cost: ${input_cost + output_cost:.6f}")

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise ValueError("Model did not return a tool_use block")

    results = tool_use.input["results"]

    # Defensive guard: if the model drops/adds items, don't silently misalign.
    if len(results) != len(case_numbers):
        results = results + ["INVALID"] * (len(case_numbers) - len(results))
        results = results[: len(case_numbers)]

    return results
 
def normalize_case_numbers_haiku(case_numbers: list[str]) -> list[dict]:
    """
    Normalizes a list of raw case numbers to the canonical
    "<prefix>-<docket>-<year>" format.
 
    Returns a list of {"index": int, "normalized": str}, one per input,
    in the original order -- same output shape as the Mistral version.
    """

    client = anthropic.Anthropic(
        api_key=os.getenv("SUPABASE_URL")
    )
    
    results = [None] * len(case_numbers)
    needs_haiku_positions = []
    needs_haiku_values = []
 
    for i, raw in enumerate(case_numbers):
        key = _cache_key(raw)
        if key in _norm_cache:
            results[i] = _norm_cache[key]
            continue
 
        regex_result = normalize_case_number_regex(raw)
        if regex_result is not None:
            _norm_cache[key] = regex_result
            results[i] = regex_result
        else:
            needs_haiku_positions.append(i)
            needs_haiku_values.append(raw)
 
    if needs_haiku_values:
        haiku_results = _normalize_via_haiku(client, needs_haiku_values)
        for pos, raw, normalized in zip(needs_haiku_positions, needs_haiku_values, haiku_results):
            results[pos] = normalized
            _norm_cache[_cache_key(raw)] = normalized
 
    return [{"index": i, "normalized": results[i]} for i in range(len(case_numbers))]
 
 #########################################################


MODEL = "claude-haiku-4-5-20251001"

TOOL_NAME = "record_financial_obligations"

# Known/normalized values are enforced via enum so the model can't drift,
# and so we don't have to restate "normalize X as Y" in prose anymore.
KNOWN_SUBTYPES = [
    # tax
    "tax", "quarterly_tax", "municipal_tax",
    # utility
    "sewer", "water", "ccmua", "combined_utilities",
    # fee
    "property_registration", "vacant_property",
    # claim
    "solar_claim",
    # lien
    "tax_lien", "utility_lien", "third_party_tax_lien",
    # advance
    "advance_reimbursement",
    # unpaid_amount (free-ish but constrained to common forms)
    "amount_due_execution", "judgment_amount", "payoff_amount", "total_amount_due",
    "other",
]

OBLIGATION_SCHEMA = {
    "type": "object",
    "properties": {
        "financial_obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "unpaid_amount", "tax", "utility", "lien", "fee",
                            "claim", "municipal_charge", "advance", "other",
                        ],
                        "description": "What the amount IS, per its governing noun phrase — not words merely nearby.",
                    },
                    "subtype": {"type": "string", "enum": KNOWN_SUBTYPES},
                    "amount": {"type": ["number", "null"], "description": "Numeric, no $ or commas."},
                    "status": {
                        "type": "string",
                        "enum": ["open", "paid", "billed", "due", "owed", "unknown"],
                    },
                    "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD or null."},
                    "period": {"type": ["string", "null"], "description": "e.g. '2025 Q3', when no exact date."},
                    "as_of": {"type": ["string", "null"], "description": "YYYY-MM-DD balance-calculated date, or null."},
                    "penalty": {"type": "boolean", "description": "true only if text explicitly states a penalty."},
                    "interest": {"type": ["number", "null"], "description": "Only if an explicit interest $ amount is given."},
                    "exists": {"type": ["boolean", "null"], "description": "true if obligation is mentioned but has no stated amount."},
                    "holder": {"type": ["string", "null"]},
                    "certificate": {"type": ["string", "null"], "description": "TSC/CTL/instrument # tied to this obligation."},
                    "description": {"type": ["string", "null"], "description": "Short summary, not copied source text."},
                },
                "required": ["category", "subtype", "amount", "status"],
            },
        }
    },
    "required": ["financial_obligations"],
}

# Condensed system prompt. The category/subtype/status *lists* now live only
# in the schema (above) — this keeps only the non-obvious reasoning guidance
# that a schema can't express: how to tell categories apart, and the
# calibration examples for edge cases.
SYSTEM_PROMPT = """You extract standardized financial obligations from NJ sheriff's sale / \
foreclosure / municipal charge / tax / utility / lien / judgment notices.

For every distinct dollar figure, ask: "what noun phrase grammatically governs this amount?" \
Classify based on what the text explicitly says the money IS — not on related words \
("lien", "tax", "charges") appearing merely nearby in the same sentence or paragraph. \
Boilerplate disclaimer language (about liability, priority, or accuracy of information) \
never determines classification of a nearby amount.

CATEGORY DISTINCTIONS:
- unpaid_amount: the WHOLE debt/sale/execution/judgment/payoff total (usually one per notice, \
occasionally two). Not tied to one specific tax period, utility, certificate, or lienholder.
- tax / utility / lien / municipal_charge / fee / claim / advance: itemized charges tied to a \
specific period, certificate, instrument, lienholder, or claim. Size of the amount never \
determines category — a large itemized charge is still itemized.
- advance: money a party paid post-judgment and is seeking reimbursement/priority for.

RULES:
- One dollar figure = one object. Never merge distinct figures unless the text presents them \
as one single total.
- amount: numeric only, strip $ and commas.
- penalty: true only if text explicitly states a penalty (not merely interest/late charges).
- interest: only an explicit interest DOLLAR amount; otherwise null.
- Exact date -> due_date/as_of as YYYY-MM-DD. Quarter/year only -> period (e.g. "2025 Q3"), \
leave due_date/as_of null. Never infer a due date from the notice date.
- If an obligation is mentioned with no stated amount: amount=null, exists=true.
- Never invent holder, certificate, amount, or date information not explicitly stated.

CALIBRATION EXAMPLES:

1) "...property taxes are due and owing in the amount of $3,976.59... pursuant to TSC #26-00890."
-> tied to a specific tax + certificate -> category=tax, amount=3976.59, certificate="TSC #26-00890"

2) "...amount due on this execution is $283,705.98... The prior liens, as per affidavit of \
consideration are not a representation of fact on the part of the Sheriff."
-> $283,705.98 is governed by "amount due on this execution" (the whole judgment). "liens" only \
appears in a following disclaimer sentence and does not describe this figure.
-> category=unpaid_amount, subtype=amount_due_execution, amount=283705.98, status=due

3) "THE AMOUNT ADVANCED WAS $10,492.22 AND THE PLAINTIFF HAS OBTAINED AN ORDER TO BE REIMBURSED..."
-> category=advance, subtype=advance_reimbursement, amount=10492.22, status=owed

Call the tool with every distinct obligation found. Do not skip any monetary figure."""


def extract_financial_obligations_haiku(raw_text: str, max_retries: int = 3) -> dict:
    """
    Extract standardized financial obligations from foreclosure text.
    Uses the service/model configured for the 'salesweb' task in the GUI.
    Falls back to Anthropic with tool-use (structured output) + prompt caching.

    Returns
    -------
    dict: {"financial_obligations": [ {...}, ... ]}
    """
    # ── Read GUI-configured settings for 'salesweb' ──────────────────────────
    try:
        from app import _settings
    except ImportError:
        _settings = {}
    sw_cfg = (_settings.get("llm_configs") or {}).get("salesweb", {})
    svc   = (sw_cfg.get("service") or "anthropic").lower().strip()
    mdl   = sw_cfg.get("model") or MODEL
    key   = sw_cfg.get("api_key") or os.getenv("SUPABASE_URL")

    print(f"[salesweb] extract_financial_obligations using service={svc}, model={mdl}")

    # ── Anthropic path: forced tool-use + prompt caching ────────────────────
    if svc == "anthropic":
        client = anthropic.Anthropic(api_key=key)
        for attempt in range(max_retries):
            try:
                response = client.messages.create(
                    model=mdl,
                    max_tokens=2048,
                    system=[
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": raw_text}],
                    tools=[
                        {
                            "name": TOOL_NAME,
                            "description": "Record the extracted financial obligations.",
                            "input_schema": OBLIGATION_SCHEMA,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    tool_choice={"type": "tool", "name": TOOL_NAME},
                )

                usage = response.usage
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
                print(
                    f"📊 tokens — input(fresh): {usage.input_tokens}, "
                    f"cache_read: {cache_read}, cache_write: {cache_write}, "
                    f"output: {usage.output_tokens}"
                )

                tool_use = next((b for b in response.content if b.type == "tool_use"), None)
                if tool_use is None:
                    raise ValueError("Model did not return a tool_use block")

                return {"financial_obligations": tool_use.input.get("financial_obligations", [])}

            except anthropic.APIStatusError as e:
                print(f"Financial obligations request failed (attempt {attempt + 1}): {e}")
                time.sleep(1)
                continue
            except Exception as e:
                print(f"Financial obligations failed: {e}")
                return {"financial_obligations": []}

        return {"financial_obligations": []}

    # ── Non-Anthropic path: call_unified_llm with structured JSON prompt ─────
    obligations_schema = {
        "type": "object",
        "properties": {
            "financial_obligations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "subtype": {"type": "string"},
                        "amount": {"type": "number"},
                        "status": {"type": "string"}
                    },
                    "required": ["category", "amount"]
                }
            }
        },
        "required": ["financial_obligations"]
    }
    for attempt in range(max_retries):
        try:
            raw = call_unified_llm(
                prompt=raw_text,
                system_prompt=SYSTEM_PROMPT,
                response_json=True,
                service=svc,
                api_key=key,
                model=mdl,
                schema=obligations_schema,
                task="salesweb",
                max_retries=1,
            )
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict) and "financial_obligations" in parsed:
                return parsed
            raise ValueError(f"Unexpected shape: {parsed}")
        except Exception as e:
            print(f"Financial obligations failed ({svc}, attempt {attempt + 1}): {e}")
            time.sleep(1)

    return {"financial_obligations": []}




# Condensed system prompt -- category/subtype/status lists now live only in
# the tool schema above. Only the non-obvious reasoning guidance stays here.
system_prompt = """
You are an expert information extraction engine.

Your ONLY job is to extract financial obligations from NJ sheriff's sale / foreclosure notices.

Return ONLY valid JSON. Do not explain anything.

Use exactly this schema:

{
  "financial_obligations": [
    {
      "category": "unpaid_amount | tax | utility | lien | fee | claim | municipal_charge | advance | other",
      "subtype": "",
      "amount": null,
      "status": "open | paid | billed | due | owed | unknown",
      "due_date": null,
      "period": null,
      "as_of": null,
      "penalty": false,
      "interest": null,
      "exists": null,
      "holder": null,
      "certificate": null,
      "description": null
    }
  ]
}

HOW TO CLASSIFY EACH DOLLAR FIGURE — REASON, DON'T PATTERN-MATCH:

For every dollar amount you find, first ask: "what noun phrase grammatically
describes what this money IS?" Find the words that directly govern the amount
(usually right before or after it), not just words that happen to appear
somewhere in the same sentence or paragraph.

Then classify based on what that governing description says:

-> "unpaid_amount": the figure represents the WHOLE debt/sale being enforced,
as a single summary total. It is described as a price, judgment, payoff, or
"the amount due" for the sale/execution/foreclosure itself — covering the
matter as a whole, not one line-item. There is typically only one (occasionally
two, e.g. a payoff and a judgment) such figure per notice, and it is not tied
to a specific tax period, utility type, or certificate/instrument number.

-> "lien" / "tax" / "utility" / "municipal_charge": the figure is described as
belonging to ONE specific, named basis — a particular tax quarter/date, a
water or sewer bill, a certificate/TSC/CTL/instrument number, or a named
lienholder. Itemized charges keep their specific category and basis even when
the dollar amount is large — the amount itself is never the deciding factor,
only what the text says the money IS for.

-> "advance": money the plaintiff paid after judgment (insurance, inspections,
taxes) that plaintiff seeks reimbursement or priority for.

CRITICAL PITFALL TO AVOID: notices often contain generic disclaimer sentences
that use words like "lien," "encumbrance," or "charges" in a general legal
sense — e.g. boilerplate about liability, priority, or accuracy of information
— WITHOUT actually describing any specific dollar figure. These sentences are
not attached to a number and must never influence how you classify a nearby
total. Before using a word like "lien" as a classification signal, confirm
that word is the grammatical subject actually describing that specific dollar
amount — not just present somewhere nearby in the paragraph.

If you are ever uncertain whether a figure is the whole-sale total or an
itemized charge, prefer "unpaid_amount" only when the figure is described as
covering the sale/execution/judgment as a whole; prefer the itemized category
whenever the text ties the amount to one named tax period, utility, or
certificate/instrument number.

CALIBRATION EXAMPLES (for reasoning pattern, not phrase-matching):

Text: "...property taxes are due and owing in the amount of $3,976.59...
pursuant to TSC #26-00890."
Reasoning: this amount is tied to a specific tax certificate and a specific
tax obligation for a named parcel -> itemized charge.
-> {"category": "tax", "subtype": "quarterly_tax", "amount": 3976.59,
    "certificate": "TSC #26-00890", "status": "owed"}

Text: "...I will expose for sale... The approximate amount due on this
execution is $283,705.98 plus interest, cost, printers' fees, Sheriff's fees
and commission. The prior liens, as per affidavit of consideration are not a
representation of fact on the part of the Sheriff."
Reasoning: "$283,705.98" is directly governed by "the amount due on this
execution" — describing the whole sale/judgment as one total. The word
"liens" appears only in the following disclaimer sentence about the accuracy
of information, which does not describe or attach to this dollar figure at
all -> whole-sale total, not a lien.
-> {"category": "unpaid_amount", "subtype": "amount_due_execution",
    "amount": 283705.98, "status": "due"}

Text: "...THE AMOUNT ADVANCED WAS $10,492.22 AND THE PLAINTIFF HAS OBTAINED
AN ORDER TO BE REIMBURSED..."
Reasoning: described as an advance the plaintiff made and seeks reimbursement
for -> advance, not a lien or unpaid_amount.
-> {"category": "advance", "subtype": "advance_reimbursement", "amount": 10492.22,
    "status": "owed"}

OTHER NORMALIZATION RULES:
- Every distinct monetary figure becomes one object. Preserve every separate amount, including multiple parcels/addresses billed separately.
- If text says "plus penalty", set penalty=true.
- If an explicit interest dollar figure is given, store it in interest.
- If a charge is mentioned but no amount is given, amount=null and exists=true.
- Normalize dates to YYYY-MM-DD when a specific date is given. If only a quarter/year is given, put it in "period" instead and leave due_date/as_of null.

Normalize categories (for tax/utility/lien/fee/claim/municipal_charge subtypes):
Taxes: tax, quarterly_tax, municipal_tax
Utilities: sewer, water, ccmua, combined_utilities
Fees: property_registration, vacant_property
Claims: solar_claim
Liens: tax_lien, utility_lien, third_party_tax_lien

Normalize statuses:
OPEN -> open | PAID -> paid | BILLED -> billed | OWED IN ARREARS -> owed | DUE -> due

If information is missing, return null. Never invent information.
"""

tools=[{
                "name": TOOL_NAME,
                "description": "Record the extracted financial obligations.",
                "input_schema": OBLIGATION_SCHEMA,
                "cache_control": {"type": "ephemeral"},
            }]

def extract_financial_obligations_groq(raw_text: str, max_retries: int = 3) -> dict:
    """
    Extract standardized financial obligations from foreclosure text using
    Groq (openai/gpt-oss-120b) with forced tool calling.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY_SECONDARY") or os.getenv("GROQ_API_KEY"))

    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0,
                reasoning_effort="low",  # gpt-oss reasoning tokens are billed as output -- this is
                                         # your biggest cost lever on Groq. Bump to "medium" only if
                                         # you see classification accuracy regress on edge cases.
                stream=False,
            )

            usage = completion.usage
            print(
                f"📊 tokens — prompt: {usage.prompt_tokens}, "
                f"completion: {usage.completion_tokens}, total: {usage.total_tokens}"
            )

            tool_calls = completion.choices[0].message.tool_calls
            if not tool_calls:
                raise ValueError("Model did not return a tool call")

            args = json.loads(tool_calls[0].function.arguments)
            return {"financial_obligations": args.get("financial_obligations", [])}

        except json.JSONDecodeError as e:
            print(f"Groq returned invalid tool arguments (attempt {attempt + 1}): {e}")
            time.sleep(1)
            continue
        except Exception as e:
            traceback.print_exc()
            print(f"Groq financial obligations failed (attempt {attempt + 1}): {e}")
            time.sleep(1)
            continue

    return {"financial_obligations": []}


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED MULTI-PROVIDER LLM CALLER (OpenRouter, Groq, Google, Anthropic)
# ══════════════════════════════════════════════════════════════════════════════
@pysnooper.snoop()
def call_unified_llm(
    prompt: str,
    system_prompt: str = "You are a precise data extraction assistant. Return valid JSON only.",
    response_json: bool = True,
    service: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    schema: Optional[dict] = None,
    task: Optional[str] = None,
    max_retries: int = 3,
) -> str:
    """
    Unified multi-provider LLM caller supporting:
      - openrouter
      - groq
      - google (gemini)
      - anthropic
    Falls back gracefully, uses task-specific settings if available, and records token costs.
    """
    import os
    try:
        from config import settings
        task_cfg_obj = settings.get_llm_config(task or "general")
        svc = (service or task_cfg_obj.service).lower().strip()
        key = api_key or task_cfg_obj.api_key
        mdl = model or task_cfg_obj.model
    except Exception:
        try:
            from app import _settings
        except ImportError:
            _settings = {}
        task_key = (task or "general").lower().strip()
        task_cfg = _settings.get("llm_configs", {}).get(task_key, {}) if isinstance(_settings.get("llm_configs"), dict) else {}
        svc = (service or task_cfg.get("service") or _settings.get("llm_service") or "groq").lower().strip()
        key = api_key or task_cfg.get("api_key") or _settings.get("llm_api_key") or ""
        mdl = model or task_cfg.get("model") or _settings.get("llm_model") or ""

    # Always reinforce schema in system prompt if provided
    if schema:
        schema_json = json.dumps(schema, indent=2)
        effective_system = (
            f"{system_prompt}\n\n"
            f"CRITICAL: You MUST respond with a JSON object strictly matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Return only valid JSON adhering to the schema. Do not output any explanatory text outside the JSON."
        )
    else:
        effective_system = system_prompt

    for attempt in range(max_retries):
        try:
            tokens_in = 0
            tokens_out = 0
            content = ""

            if svc == "openrouter":
                effective_key = key or os.getenv("OPENROUTER_API_KEY", "")
                effective_model = mdl or "anthropic/claude-3.5-haiku"
                import requests
                headers = {
                    "Authorization": f"Bearer {effective_key}",
                    "Content-Type": "application/json",
                }
                body = {
                    "model": effective_model,
                    "messages": [
                        {"role": "system", "content": effective_system},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                }
                if schema:
                    body["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": task_key or "data", "strict": True, "schema": schema}
                    }
                elif response_json:
                    body["response_format"] = {"type": "json_object"}

                resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=60)
                if resp.status_code == 400 and schema:
                    body["response_format"] = {"type": "json_object"}
                    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=60)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["choices"][0]["message"]["content"]
                usage = res_data.get("usage", {})
                tokens_in = usage.get("prompt_tokens", len(prompt) // 4)
                tokens_out = usage.get("completion_tokens", len(content) // 4)

            elif svc == "anthropic":
                effective_key = key or os.getenv("ANTHROPIC_API_KEY")
                effective_model = mdl or "claude-haiku-4-5-20251001"
                import anthropic as _anthropic
                client = _anthropic.Anthropic(api_key=effective_key)

                kwargs = {
                    "model": effective_model,
                    "max_tokens": 4096,
                    "system": effective_system,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                }
                if schema:
                    tool_name = f"extract_{task_key}" if task_key else "record_extracted_data"
                    kwargs["tools"] = [{
                        "name": tool_name,
                        "description": f"Extract structured data strictly matching the schema for {task_key or 'task'}",
                        "input_schema": schema,
                    }]
                    kwargs["tool_choice"] = {"type": "tool", "name": tool_name}
                msg = client.messages.create(**kwargs)
                if schema:
                    tool_use = next((b for b in msg.content if b.type == "tool_use"), None)
                    if tool_use:
                        content = json.dumps(tool_use.input)
                    else:
                        content = msg.content[0].text if msg.content else "{}"
                else:
                    content = msg.content[0].text if msg.content else ""

                tokens_in = getattr(msg.usage, "input_tokens", len(prompt) // 4)
                tokens_out = getattr(msg.usage, "output_tokens", len(content) // 4)

            elif svc in ("google", "gemini"):
                effective_key = key or os.getenv("GEMINI_API_KEY", "")
                effective_model = mdl or "gemini-2.0-flash"
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{effective_model}:generateContent?key={effective_key}"
                headers = {"Content-Type": "application/json"}
                gen_config = {"temperature": 0}
                if response_json:
                    gen_config["responseMimeType"] = "application/json"
                if schema:
                    gen_config["responseSchema"] = schema
                body = {
                    "contents": [{"parts": [{"text": f"{effective_system}\n\n{prompt}"}]}],
                    "generationConfig": gen_config
                }
                resp = requests.post(url, headers=headers, json=body, timeout=60)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                usage = res_data.get("usageMetadata", {})
                tokens_in = usage.get("promptTokenCount", len(prompt) // 4)
                tokens_out = usage.get("candidatesTokenCount", len(content) // 4)

            elif svc in ("freellmapi", "freellm", "logfare", "openai"):
                if svc == "openai":
                    effective_key = key or os.getenv("OPENAI_API_KEY", "")
                    effective_base_url = os.getenv("OPENAI_BASE_URL", None)
                    effective_model = mdl or "gpt-4o-mini"
                else:
                    effective_key = key or os.getenv("FREELLMAPI_API_KEY", "")
                    effective_base_url = os.getenv("FREELLMAPI_BASE_URL", "http://localhost:5173/v1")
                    effective_model = mdl or "gemma-4-26b"

                from openai import OpenAI as OpenAIClient
                client_kwargs = {"api_key": effective_key}
                if effective_base_url:
                    client_kwargs["base_url"] = effective_base_url
                client = OpenAIClient(**client_kwargs)

                kwargs = {
                    "model": effective_model,
                    "messages": [
                        {"role": "system", "content": effective_system},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                }
                if schema:
                    try:
                        kwargs["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {"name": task_key or "data", "schema": schema}
                        }
                        resp = client.chat.completions.create(**kwargs)
                    except Exception:
                        kwargs["response_format"] = {"type": "json_object"}
                        resp = client.chat.completions.create(**kwargs)
                elif response_json:
                    kwargs["response_format"] = {"type": "json_object"}
                    
                    resp = client.chat.completions.create(**kwargs)
                else:
                    resp = client.chat.completions.create(**kwargs)

                content = resp.choices[0].message.content
                if hasattr(resp, "usage") and resp.usage:
                    tokens_in = getattr(resp.usage, "prompt_tokens", len(prompt) // 4)
                    tokens_out = getattr(resp.usage, "completion_tokens", len(content) // 4)
                else:
                    tokens_in = len(prompt) // 4
                    tokens_out = len(content) // 4

            else:  # Default to Groq
                effective_key = key or os.getenv("GROQ_API_KEY", "")
                effective_model = mdl or "openai/gpt-oss-120b"
                from groq import Groq
                client = Groq(api_key=effective_key)
                kwargs = {
                    "model": effective_model,
                    "messages": [
                        {"role": "system", "content": effective_system},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                }
                if schema:
                    try:
                        kwargs["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {"name": task_key or "data", "schema": schema}
                        }
                        resp = client.chat.completions.create(**kwargs)
                    except Exception:
                        kwargs["response_format"] = {"type": "json_object"}
                        resp = client.chat.completions.create(**kwargs)
                elif response_json:
                    kwargs["response_format"] = {"type": "json_object"}
                    resp = client.chat.completions.create(**kwargs)
                else:
                    resp = client.chat.completions.create(**kwargs)

                content = resp.choices[0].message.content
                if hasattr(resp, "usage") and resp.usage:
                    tokens_in = getattr(resp.usage, "prompt_tokens", len(prompt) // 4)
                    tokens_out = getattr(resp.usage, "completion_tokens", len(content) // 4)
                else:
                    tokens_in = len(prompt) // 4
                    tokens_out = len(content) // 4

            # Clean JSON if markdown fenced
            if response_json and content:
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r"\s*```$", "", cleaned)
                content = cleaned.strip()

            # Track cost
            try:
                from ai.llm_cost_tracker import record_llm_cost
                record_llm_cost(task_key, effective_model, tokens_in, tokens_out, service=svc)
            except Exception as ce:
                print(f"[LLM Cost] Could not record cost: {ce}")

            return content

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.5)
            else:
                raise


def get_freellmapi_client(api_key: Optional[str] = None, base_url: Optional[str] = None):
    """
    Returns an OpenAI-compatible client configured for FreeLLMAPI (Logfare).
    """
    import os

    from openai import OpenAI
    key = api_key or os.getenv("FREELLMAPI_API_KEY", "")
    url = base_url or os.getenv("FREELLMAPI_BASE_URL", "http://localhost:5173/v1")
    return OpenAI(api_key=key, base_url=url)


def call_freellmapi(
    prompt: str,
    system_prompt: str = "You are a precise data extraction assistant. Return valid JSON only.",
    model: Optional[str] = "gemma-4-26b",
    response_json: bool = True,
    schema: Optional[dict] = None,
    api_key: Optional[str] = None,
    task: Optional[str] = None,
) -> str:
    """
    Convenience wrapper to call FreeLLMAPI service via call_unified_llm.
    """
    return call_unified_llm(
        prompt=prompt,
        system_prompt=system_prompt,
        response_json=response_json,
        service="freellmapi",
        api_key=api_key,
        model=model,
        schema=schema,
        task=task,
    )

