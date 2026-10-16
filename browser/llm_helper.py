# pywinrt imports
import hashlib
import re
import time
from pathlib import Path
from typing import List, Optional

import anthropic
import pdfplumber
import pysnooper
from bs4 import BeautifulSoup
from mistralai import DocumentURLChunk, Mistral
from mistralai.models.sdkerror import SDKError
from pydantic import BaseModel, Field
from tqdm import tqdm

import os
import json
from dotenv import load_dotenv

load_dotenv()
mistral_api = os.getenv("MISTRAL_API_KEY", "")


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
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                }
                if response_json:
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
                msg = client.messages.create(
                    model=effective_model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                content = msg.content[0].text
                tokens_in = getattr(msg.usage, "input_tokens", len(prompt) // 4)
                tokens_out = getattr(msg.usage, "output_tokens", len(content) // 4)

            elif svc in ("google", "gemini"):
                effective_key = key or os.getenv("GEMINI_API_KEY", "")
                effective_model = mdl or "gemini-2.0-flash"
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{effective_model}:generateContent?key={effective_key}"
                headers = {"Content-Type": "application/json"}
                body = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
                    "generationConfig": {"temperature": 0}
                }
                if response_json:
                    body["generationConfig"]["responseMimeType"] = "application/json"
                resp = requests.post(url, headers=headers, json=body, timeout=60)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                usage = res_data.get("usageMetadata", {})
                tokens_in = usage.get("promptTokenCount", len(prompt) // 4)
                tokens_out = usage.get("candidatesTokenCount", len(content) // 4)

            else:  # Default to Groq
                effective_key = key or os.getenv("GROQ_API_KEY", "")
                effective_model = mdl or "openai/gpt-oss-120b"
                from groq import Groq
                client = Groq(api_key=effective_key)
                kwargs = {
                    "model": effective_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                }
                if response_json:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content
                if hasattr(resp, "usage") and resp.usage:
                    tokens_in = getattr(resp.usage, "prompt_tokens", len(prompt) // 4)
                    tokens_out = getattr(resp.usage, "completion_tokens", len(content) // 4)
                else:
                    tokens_in = len(prompt) // 4
                    tokens_out = len(content) // 4

            # Track cost
            try:
                from ai.llm_cost_tracker import record_llm_cost
                record_llm_cost(task_key, effective_model, tokens_in, tokens_out, service=svc)
            except Exception as ce:
                print(f"[LLM Cost] Could not record cost: {ce}")

            return content

        except Exception as e:
            print(f"[call_unified_llm] Attempt {attempt + 1}/{max_retries} failed via {svc} for task '{task_key}': {e}")
            if attempt < max_retries - 1:
                time.sleep(1.5)
            else:
                raise


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
        schema=FinalJudgmentData.model_json_schema(),
        api_key=key,
        model=mdl,
        task="judgment"
    )
    try:
        return json.loads(raw)
    except Exception:
        return raw

def extract_complaint(file_path):
    """Extract foreclosure complaint data using Mistral AI."""

    # Create log directory
    os.makedirs(os.path.join(os.path.dirname(file_path), "llm_helper_logs"), exist_ok=True)
    log_file = os.path.join(os.path.dirname(file_path), "llm_helper_logs",
                            f"extract_complaint_{os.path.basename(os.path.dirname(file_path))}.log")
    data_file = os.path.join(os.path.dirname(file_path), "llm_helper_logs",
                             f"complaint_extracted_data_{os.path.basename(os.path.dirname(file_path))}.txt")

    with pysnooper.snoop(log_file):
        complaint_text = pdf_to_text(file_path)

        complain_prompt = f"""
        You are extracting data from a foreclosure complaint.

        Extract ONLY information explicitly stated in the document.

        Rules:
        - Do not guess.
        - Use null for missing values.
        - Return valid JSON matching the provided schema.
        - Extract every plaintiff.
        - Extract every defendant.
        - Include defendant numbers if listed (Defendant #1, Defendant #2, etc.).
        - Extract defendant addresses if available.
        - Extract relationships such as:
        - spouse
        - heir
        - unknown tenant
        - occupant
        - trustee
        - borrower
        - co-borrower
        - personal representative
        - Extract the mortgage execution date.
        - Extract amount owed.
        - Extract the original mortgage amount.
        - Extract all liens, judgments, tax liens, HOA liens, municipal liens, and subordinate mortgages.
        - For each lien include lienholder, amount, date, and recording information when available.
        - Extract the interest rate on the mortgage if stated.
        - Extract whether the homeowner is deceased (true/false). Look for language
        such as "deceased", "late", "estate of", "heir", or similar indicators.
        - If the homeowner is deceased, extract the date of death if stated.

        IMPORTANT:

        Determine whether homeowner, or defendant is deceased.

        The field "homeowner_deceased" MUST ALWAYS be either true or false.

        Set it to:
        - true only if the complaint explicitly indicates that homeowner or defendant is deceased.
        - false if there is no explicit indication that any homeowner or defendant is deceased.

        Never return null for homeowner_deceased.

        If a deceased person is identified:

        - Extract the FULL NAME of the deceased person.
        - Extract the date of death if stated.
        - Extract the exact text that indicates the death.
        - Do not infer a name from heirs alone.
        - If the document says "Estate of John Smith", then the deceased person's name is "John Smith".
        - If the document says "Unknown Heirs of John Smith", then the deceased person's name is "John Smith".
        - If multiple deceased persons exist, extract all of them.

        PROPERTY ADDRESS EXTRACTION:

        Extract the property address with extreme precision.

        Rules for property address:
        - Look for "property address", "property located at", "premises", "subject property", or similar indicators.
        - Extract the FULL address including street number, street name, city, state, and ZIP code.
        - If the address has multiple lines, combine them.
        - If the complaint mentions "commonly known as" followed by an address, extract that.
        - Also look for address in the caption or case title.
        - If the property address is listed in a separate section (like "Schedule A" or "Exhibit A"), extract it.
        - If the address is split between street address and city/state, combine them.

        Example formats to extract:
        - "123 Main Street, Anytown, NJ 07001"
        - "123 Main Street, Anytown, New Jersey 07001"
        - "123 Main Street, Anytown, NJ"
        - "123 Main Street, Anytown, New Jersey"
        - "123 Main Street, Anytown, NJ 07001-1234"

        BLOCK AND LOT EXTRACTION:

        Extract the block and lot number for the property.

        Rules for block and lot:
        - Look for "block", "lot", "Block", "Lot", "BLOCK", "LOT" in the document.
        - Also look for "qualifier", "Q", "C" which are sometimes used with block/lot.
        - The block and lot may be in formats like:
          - "Block 123, Lot 456"
          - "Block: 123, Lot: 456"
          - "BLOCK 123 LOT 456"
          - "Block 123.01, Lot 456.07"
          - "Block 123, Lot 456, Qualifier C"
          - "Block 123, Lot 456, Q"
        - Look in the property description section.
        - Look in the legal description.
        - Look in the schedule or exhibit sections.
        - Extract the full block and lot as they appear.
        - If both block and lot are present, extract both.

        Extract these fields:
        - property_address: Full street address (string)
        - property_city: City name (string)
        - property_state: State (string, usually NJ)
        - property_zip: ZIP code (string)
        - block: Block number (string, preserve formatting like "123" or "123.01")
        - lot: Lot number (string, preserve formatting like "456" or "456.07")

        IMPORTANT:
        - If the block and lot are mentioned in multiple places, use the most specific one.
        - If the block/lot is in a legal description that's hard to parse, extract the full legal description too.
        - If only partial information is available (e.g., only block or only lot), extract what's available.
        - If no block/lot information is found, set to null.
        - Do not infer block/lot from other information.

        Document:

        {complaint_text}
        """

        client = get_mistral_client()
        response = client.chat.complete(
            model="mistral-small-2506",
            messages=[
                {
                    "role": "user",
                    "content": complain_prompt
                }
            ],
            response_format={
                "type": "json_object",
                "schema": ForeclosureComplaint.model_json_schema()
            }
        )
        data = response.choices[0].message.content
        with open(data_file, 'w') as f:
            f.write(data)
        return data


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


# Python example using Mistral API with structured outputs


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


def pdf_to_text(
        pdf_path: str,
        min_chars: int = 150,
        max_pages: int = None) -> str:
    results = {}
    ocr_pages = []
    direct_count = 0
    ocr_count = 0

    print("🔎 Scanning pages for selectable text...")
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        pages_to_scan = pdf.pages[:max_pages] if max_pages else pdf.pages

        for i, page in enumerate(
                tqdm(
                    pages_to_scan,
                    total=len(pages_to_scan),
                    unit="page",
                    desc="Scanning"
                ),
                start=1
        ):
            text = page.extract_text() or ""
            char_count = len(text.strip())

            if char_count >= min_chars:
                results[i] = text.strip()
                direct_count += 1
            else:
                ocr_pages.append(i)
                ocr_count += 1

    print(f"\n✅ Scan complete ({len(pages_to_scan)}/{total_pages} pages):")
    print(f"   {direct_count} pages → direct extraction")
    print(f"   {ocr_count}  pages → need OCR\n")

    if not ocr_pages:
        print("🎉 No OCR needed — all pages had selectable text!")

    else:
        print(f"🔍 Processing {ocr_count} pages via Mistral OCR...")

        client = get_mistral_client()
        pdf_path_obj = Path(pdf_path)

        response_dict = None
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"🔄 Mistral OCR attempt "
                    f"{attempt}/{max_retries}..."
                )

                # Upload PDF
                uploaded_file = client.files.upload(
                    file={
                        "file_name": pdf_path_obj.stem,
                        "content": pdf_path_obj.read_bytes(),
                    },
                    purpose="ocr",
                )

                # Get signed URL
                signed_url = client.files.get_signed_url(
                    file_id=uploaded_file.id,
                    expiry=1
                )

                # Process OCR
                pdf_response = client.ocr.process(
                    document=DocumentURLChunk(
                        document_url=signed_url.url
                    ),
                    model="mistral-ocr-latest",
                    include_image_base64=True
                )

                # Convert response to dictionary
                response_dict = json.loads(
                    pdf_response.model_dump_json()
                )

                print("✅ Mistral OCR complete.")
                break

            except Exception as e:
                print(
                    f"⚠️ Mistral OCR attempt "
                    f"{attempt}/{max_retries} failed:"
                )
                print(f"   {type(e).__name__}: {e}")

                if attempt == max_retries:
                    print(
                        "❌ Mistral OCR failed after "
                        f"{max_retries} attempts."
                    )
                    raise

                wait_time = 2 * attempt
                print(
                    f"⏳ Retrying in {wait_time} seconds..."
                )
                time.sleep(wait_time)

        print("📄 Mapping OCR results...")

        for i, page_data in enumerate(
                tqdm(
                    response_dict.get("pages", []),
                    unit="page",
                    desc="Mapping OCR"
                ),
                start=1
        ):
            # Only store OCR result if this page was flagged for OCR
            if i in ocr_pages:
                results[i] = page_data.get(
                    "markdown",
                    "[OCR returned empty]"
                )

    # Rebuild final document
    all_pages_text = [
        f"--- Page {n} "
        f"[{'direct' if n not in ocr_pages else 'ocr'}] ---\n"
        f"{results.get(n, '[Page Text Missing]')}"
        for n in sorted(results.keys())
    ]

    return "\n\n".join(all_pages_text)

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

def get_obituary_link_data(obituary_text):
    client = get_mistral_client()

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

    response = client.chat.complete(
        model="mistral-small-2506",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_object",
            "schema": ObituaryData.model_json_schema()
        }
    )

    return json.loads(response.choices[0].message.content), obituary_text


def get_bankruptcy_case_status(bankruptcy_path):
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
    client = get_mistral_client()
    response = client.chat.complete(
        model="mistral-small-2506",
        messages=[{"role": "user", "content": bankruptcy_status_prompt}],
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content


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


from typing import List, Optional

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


def extract_financial_obligations(raw_text: str, save_path: str = None):
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
            if save_path:
                save_json_file(json.loads(response.choices[0].message.content), generate_filename(suffix=save_path))
            return json.loads(response.choices[0].message.content)
        except SDKError:
            time.sleep(1)
            continue
        except Exception as e:
            print(f"Mistral financial obligations failed for {raw_text}: {e}")
            return {"financial_obligations": []}


def save_json_file(data: dict, filepath: str) -> None:
    """
    Save JSON data to a file with proper formatting.
    
    Parameters
    ----------
    data : dict
        The JSON data to save.
    filepath : str
        Path where the JSON file should be saved.
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    
    # Save with pretty formatting
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Financial obligations saved to: {filepath}")


def generate_filename(prefix: str = "financial_obligations", suffix: str = None) -> str:
    """
    Generate a timestamped filename.
    
    Parameters
    ----------
    prefix : str
        Prefix for the filename.
    suffix : str, optional
        Additional suffix before the extension.
    
    Returns
    -------
    str
        Generated filename with timestamp.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if suffix:
        return f"{prefix}_{suffix}_{timestamp}.json"
    return f"{prefix}_{timestamp}.json"

def extract_financial_obligations_haiku(raw_text: str):
    """
    Extract standardized financial obligations from foreclosure text
    using Claude Haiku 4.5.
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

    client = anthropic.Anthropic(
        api_key=os.getenv("SUPABASE_URL")
    )

    while True:
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": raw_text
                    }
                ]
            )

            # Anthropic returns content as a list of content blocks.
            content = "".join(
                block.text
                for block in response.content
                if block.type == "text"
            ).strip()

            # Safety cleanup in case the model still returns fences.
            if content.startswith("```json"):
                content = content[7:]

            if content.startswith("```"):
                content = content[3:]

            if content.endswith("```"):
                content = content[:-3]

            content = content.strip()

            result = json.loads(content)

            # Make sure the expected structure exists.
            if not isinstance(result, dict):
                raise ValueError("Claude returned a non-object JSON response.")

            if "financial_obligations" not in result:
                raise ValueError(
                    "Claude response is missing 'financial_obligations'."
                )

            if not isinstance(result["financial_obligations"], list):
                raise ValueError(
                    "'financial_obligations' must be a list."
                )

            return result

        except anthropic.APIError as e:
            print(f"Claude Haiku financial obligations request failed: {e}")
            time.sleep(1)
            continue

        except json.JSONDecodeError as e:
            print(f"Claude Haiku returned invalid JSON: {e}")
            return {
                "financial_obligations": []
            }

        except Exception as e:
            print(f"Claude Haiku financial obligations failed: {e}")
            return {
                "financial_obligations": []
            }




def get_bankruptcy_case_status_haiku(bankruptcy_path):
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

    # Initialize Anthropic client
    client = anthropic.Anthropic(
        api_key=os.getenv("SUPABASE_URL")
    )

    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",  # Using Claude Haiku 4.5
                max_tokens=4096,
                temperature=0,  # Deterministic for legal analysis
                system="You are a legal document analyst specializing in bankruptcy and foreclosure proceedings. Return only valid JSON.",
                messages=[
                    {
                        "role": "user",
                        "content": bankruptcy_status_prompt
                    }
                ]
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
            # Extract the response content
            content = "".join(
                block.text
                for block in response.content
                if block.type == "text"
            ).strip()

            # Safety cleanup in case the model returns fences
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Parse JSON response
            result = json.loads(content)

            # Validate required fields
            required_fields = [
                "bankruptcy_case_status",
                "foreclosure_permitted",
                "basis",
                "justification",
                "case_number",
                "relevant_date",
                "confidence"
            ]
            
            if all(field in result for field in required_fields):
                return result
            else:
                missing_fields = [f for f in required_fields if f not in result]
                raise ValueError(f"Missing required fields: {missing_fields}")

        except anthropic.APIError as e:
            print(f"Claude Haiku bankruptcy status request failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                return {
                    "bankruptcy_case_status": "unknown",
                    "foreclosure_permitted": "unknown",
                    "basis": f"Error after {max_retries} attempts: {str(e)}",
                    "justification": "Failed to analyze document due to API error.",
                    "case_number": None,
                    "relevant_date": None,
                    "confidence": 0
                }

        except json.JSONDecodeError as e:
            print(f"Claude Haiku returned invalid JSON: {e}")
            print(f"Raw response: {content[:200]}...")  # Print first 200 chars for debugging
            return {
                "bankruptcy_case_status": "unknown",
                "foreclosure_permitted": "unknown",
                "basis": "Failed to parse JSON response",
                "justification": "The model did not return valid JSON.",
                "case_number": None,
                "relevant_date": None,
                "confidence": 0
            }

        except Exception as e:
            print(f"Claude Haiku bankruptcy status failed: {e}")
            return {
                "bankruptcy_case_status": "unknown",
                "foreclosure_permitted": "unknown",
                "basis": f"Error: {str(e)}",
                "justification": "An unexpected error occurred while analyzing the document.",
                "case_number": None,
                "relevant_date": None,
                "confidence": 0
            }
#######################################
TOOL_NAME = "extract_foreclosure_complaint"

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


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_path(log_dir: str, doc_hash: str) -> str:
    return os.path.join(log_dir, f"complaint_cache_{doc_hash}.json")


def extract_complaint_anthropic(file_path):
    """Extract foreclosure complaint data using Claude Haiku 4.5."""
    log_dir = os.path.join(os.path.dirname(file_path), "llm_helper_logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"extract_complaint_{os.path.basename(os.path.dirname(file_path))}.log"
    )
    data_file = os.path.join(
        log_dir, f"complaint_extracted_data_{os.path.basename(os.path.dirname(file_path))}.txt"
    )
    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    with pysnooper.snoop(log_file):
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

        schema = ForeclosureComplaint.model_json_schema()

        max_retries = 3
        retry_delay = 1

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
                            "content": COMPLAINT_INSTRUCTIONS_BLOCK + complaint_text,
                        }
                    ],
                    tools=[
                        {
                            "name": TOOL_NAME,
                            "description": "Record the extracted foreclosure complaint data.",
                            "input_schema": schema,
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
                
                # Estimate cost (Haiku pricing: ~$0.25/1M input, ~$1.25/1M output)
                input_cost = (input_tokens / 1_000_000) * 0.25
                output_cost = (output_tokens / 1_000_000) * 1.25
                print(f"   Estimated cost: ${input_cost + output_cost:.6f}")

                tool_use = next(
                    (b for b in response.content if b.type == "tool_use"), None
                )
                if tool_use is None:
                    raise ValueError("Model did not return a tool_use block")

                data = json.dumps(tool_use.input)

                with open(data_file, "w") as f:
                    f.write(data)
                with open(cache_file, "w") as f:
                    f.write(data)

                return data

            except anthropic.APIError as e:
                print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
#######################################



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


def match_property_address_ling(target_address: str, candidate_addresses: list):
    """
    Uses Ling through OpenRouter to decide which candidate address,
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
                            "content": user_content
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
                timeout=60
            )

            response.raise_for_status()

            result = response.json()

            content = result["choices"][0]["message"]["content"]

            return json.loads(content)

        except requests.RequestException as e:
            print(f"OpenRouter request failed for '{target_address}': {e}")
            time.sleep(1)
            continue

        except Exception as e:
            print(f"Ling address match failed for '{target_address}': {e}")

            return {
                "best_match_index": None,
                "matched_address": None,
                "confidence": "none",
                "reasoning": f"error: {e}"
            }


def match_property_address_haiku(target_address: str, candidate_addresses: list):
    """
    Uses Claude Haiku 4.5 to decide which candidate address,
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

    client = anthropic.Anthropic(
        api_key=os.getenv("SUPABASE_URL")
    )

    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_content
                    }
                ]
            )

            # Anthropic returns a list of content blocks.
            content = "".join(
                block.text
                for block in response.content
                if block.type == "text"
            ).strip()

            # Safety cleanup in case Haiku returns markdown fences.
            if content.startswith("```json"):
                content = content[7:]

            elif content.startswith("```"):
                content = content[3:]

            if content.endswith("```"):
                content = content[:-3]

            content = content.strip()

            result = json.loads(content)

            # Validate required fields
            required_fields = [
                "best_match_index",
                "matched_address",
                "confidence",
                "reasoning"
            ]

            if not all(field in result for field in required_fields):
                raise ValueError("Missing required fields in response")

            # Validate confidence value
            if result["confidence"] not in [
                "high",
                "medium",
                "low",
                "none"
            ]:
                raise ValueError(
                    f"Invalid confidence value: {result['confidence']}"
                )

            # Validate returned index actually exists in candidates
            if result["best_match_index"] is not None:
                valid_indices = {
                    candidate["index"]
                    for candidate in candidate_addresses
                    if isinstance(candidate, dict) and "index" in candidate
                }

                if result["best_match_index"] not in valid_indices:
                    raise ValueError(
                        f"Invalid candidate index returned: "
                        f"{result['best_match_index']}"
                    )

            return result

        except anthropic.APIError as e:
            print(
                f"Claude Haiku address match failed for "
                f"'{target_address}' "
                f"(attempt {attempt + 1}/{max_retries}): {e}"
            )

            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return {
                    "best_match_index": None,
                    "matched_address": None,
                    "confidence": "none",
                    "reasoning": (
                        f"error after {max_retries} attempts: {e}"
                    )
                }

        except json.JSONDecodeError as e:
            print(
                f"Claude Haiku returned invalid JSON for "
                f"'{target_address}' "
                f"(attempt {attempt + 1}/{max_retries}): {e}"
            )

            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return {
                    "best_match_index": None,
                    "matched_address": None,
                    "confidence": "none",
                    "reasoning": (
                        f"invalid JSON after {max_retries} attempts: {e}"
                    )
                }

        except Exception as e:
            print(
                f"Claude Haiku address match failed for "
                f"'{target_address}' "
                f"(attempt {attempt + 1}/{max_retries}): {e}"
            )

            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return {
                    "best_match_index": None,
                    "matched_address": None,
                    "confidence": "none",
                    "reasoning": (
                        f"error after {max_retries} attempts: {e}"
                    )
                }