"""
ollama_helper.py
----------------
Local LLM integration via Ollama for intelligent scraper recovery.
Ollama is only called when something is already broken — not on the happy path.
"""

import json

import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"  # explicit IP, not localhost
MODEL = "qwen2.5:3b"

# ══════════════════════════════════════════════════════════════════════════════
# STEP DESCRIPTIONS
# What each step actually does — sent to Ollama so it understands context
# ══════════════════════════════════════════════════════════════════════════════

STEP_DESCRIPTIONS = {
    'navigate_to_url':    'Open the clerk website homepage and wait for it to fully load',
    'navigate_to_search': 'Find and navigate to the case search form on the clerk website',
    'search_case_number': 'Type the case number into the search field and submit the form to find the case',
    'navigate_to_files':  'From the search results, click into the case record and open the docket/documents tab',
    'trigger_download':   'Click the document link in the docket table to trigger a PDF download',
    'login':              'Enter credentials and log into the court portal',
}

# What a successful outcome looks like for each step
STEP_EXPECTED_OUTCOMES = {
    'navigate_to_url':    'The clerk website homepage is loaded and visible',
    'navigate_to_search': 'A search form with a case number input field is visible',
    'search_case_number': 'Search results appear showing the case or a case details page loads',
    'navigate_to_files':  'A docket table with document rows is visible on the page',
    'trigger_download':   'A PDF file starts downloading to the local folder',
    'login':              'User is logged in and redirected to the search or dashboard page',
}

# County-specific context hints
COUNTY_CONTEXT = {
    'oc':         'Orange County Florida clerk site (myorangeclerk.com). Requires navigating through search filters.',
    'lee':        'Lee County Florida clerk site (matrix.leeclerk.org). Sometimes returns VPN blocks.',
    'bw':         'Broward County Florida clerk site (browardclerk.org). Prone to VPN-related blocks and CAPTCHAs.',
    'md':         'Miami-Dade County Florida clerk site. Requires login with credentials.',
    'pb':         'Palm Beach County Florida clerk site (mypalmbeachclerk.com). Has a guest access button.',
    'seminole':   'Seminole County Florida clerk site (courtrecords.seminoleclerk.org).',
    'sarasota':   'Sarasota County Florida clerk site (sarasotaclerk.com). Uses Telerik grid for docket table.',
    'manatee':    'Manatee County Florida clerk site (records.manateeclerk.com).',
    'volusia':    'Volusia County Florida clerk site (ccms.clerk.org).',
    'polk':       'Polk County Florida clerk site (court.polk-county.net).',
    'brevard':    'Brevard County Florida clerk site (vmatrix1.brevardclerk.us). Older UI.',
    'osceola':    'Osceola County Florida clerk site (courts.osceolaclerk.com).',
    'dv':         'Duval County Florida clerk site (core.duvalclerk.com).',
    'nj':         'New Jersey courts portal (njcourts.gov). Requires login and has CAPTCHA protection.',
    'new jersey': 'New Jersey courts portal (njcourts.gov). Requires login and has CAPTCHA protection.',
}


# ══════════════════════════════════════════════════════════════════════════════
# CORE API CALL
# ══════════════════════════════════════════════════════════════════════════════

def ask_ollama(prompt, timeout=30):
    """Send a prompt to Ollama and return the response text. Returns None on failure."""
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,   # low temp = more deterministic decisions
                "num_predict": 200,   # we only need short answers
            }
        }, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        print("⚠️ Ollama not running — skipping LLM assist")
        return None
    except Exception as e:
        print(f"⚠️ Ollama error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SHOULD RETRY
# ══════════════════════════════════════════════════════════════════════════════

def should_retry(step_name, county_name, error_description, attempt_number,
                 page_text=None, exception_text=None):
    """
    Ask Ollama whether to retry a failed step or give up.
    Returns True = retry, False = give up.
    Falls back to simple counter if Ollama is unavailable.
    """
    county_lower = county_name.lower()
    county_hint = COUNTY_CONTEXT.get(county_lower, f"{county_name} county court clerk website")
    step_desc = STEP_DESCRIPTIONS.get(step_name, f"perform step: {step_name}")
    expected = STEP_EXPECTED_OUTCOMES.get(step_name, "page loads and expected elements are present")

    page_summary = ""
    if page_text:
        cleaned = page_text.strip()[:800]
        page_summary = f"\nPAGE TEXT RIGHT NOW:\n{cleaned}"

    exception_summary = ""
    if exception_text:
        cleaned_ex = exception_text.strip()[:400]
        exception_summary = f"\nEXCEPTION:\n{cleaned_ex}"

    prompt = f"""You are helping a court document scraper recover from a failed step.

COUNTY: {county_name}
SITE CONTEXT: {county_hint}
STEP: {step_name}
WHAT THIS STEP DOES: {step_desc}
EXPECTED OUTCOME: {expected}
ERROR: {error_description}{exception_summary}
ATTEMPTS SO FAR: {attempt_number}{page_summary}

Should the scraper RETRY this step or GIVEUP on this case?

Rules:
- RETRY if: timeout, slow page load, network blip, VPN issue, spinner still visible, temporary block
- GIVEUP if: case not found, access denied, invalid case number, login failed permanently, same error {attempt_number}+ times with no change, page has completely unrelated content

Reply with one word only: RETRY or GIVEUP"""

    answer = ask_ollama(prompt, timeout=20)
    if answer is None:
        # Fallback: retry up to 3 times
        return attempt_number < 3

    return "RETRY" in answer.upper()


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSE PAGE STATE
# ══════════════════════════════════════════════════════════════════════════════

def diagnose_page_state(page_text, county_name, expected_state,
                        step_name=None, exception_text=None, verifier_description=None):
    """
    Given the page's visible text, ask Ollama what state the page is in
    and what the scraper should do next.

    Returns a dict: {"state": "...", "action": "reload|retry|skip|wait|login", "reason": "..."}
    """
    county_lower = county_name.lower()
    county_hint = COUNTY_CONTEXT.get(county_lower, f"{county_name} county court clerk website")
    step_desc = STEP_DESCRIPTIONS.get(step_name, "") if step_name else ""
    expected_outcome = STEP_EXPECTED_OUTCOMES.get(step_name, "") if step_name else ""

    step_context = ""
    if step_name:
        step_context = f"\nLAST STEP RUN: {step_name} — {step_desc}"
    if expected_outcome:
        step_context += f"\nEXPECTED AFTER STEP: {expected_outcome}"
    if verifier_description:
        step_context += f"\nVERIFIER THAT FAILED: {verifier_description}"

    exception_summary = ""
    if exception_text:
        exception_summary = f"\nEXCEPTION:\n{exception_text.strip()[:400]}"

    prompt = f"""You are helping a court document scraper understand an unexpected page state.

COUNTY: {county_name}
SITE CONTEXT: {county_hint}
EXPECTED PAGE STATE: {expected_state}{step_context}{exception_summary}

ACTUAL PAGE TEXT (first 800 chars):
{page_text.strip()[:800]}

What state is the page in and what should the scraper do?

Possible actions:
- reload: page errored or is blank, reload and try again
- retry: page loaded but expected elements not ready yet, wait and retry
- wait: page is still loading (spinner, loading indicator visible)
- login: session expired or login page appeared unexpectedly  
- skip: case genuinely not found or access permanently denied

Reply ONLY with this exact JSON format, nothing else:
{{"state": "brief description of what you see", "action": "one of: reload|retry|wait|login|skip", "reason": "brief reason for this action"}}"""

    answer = ask_ollama(prompt, timeout=25)

    if answer is None:
        return {"state": "unknown", "action": "retry", "reason": "Ollama unavailable"}

    try:
        clean = answer.replace("```json", "").replace("```", "").strip()
        # Find JSON object in response in case model adds extra text
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start != -1 and end > start:
            clean = clean[start:end]
        return json.loads(clean)
    except Exception:
        # If JSON parse fails, try to extract action keyword from raw text
        text_upper = answer.upper()
        for action in ["RELOAD", "RETRY", "WAIT", "LOGIN", "SKIP"]:
            if action in text_upper:
                return {"state": "unknown", "action": action.lower(), "reason": answer[:100]}
        return {"state": "unknown", "action": "retry", "reason": answer[:100]}


# ══════════════════════════════════════════════════════════════════════════════
# FIND LOCATOR
# ══════════════════════════════════════════════════════════════════════════════

def find_locator(page_html, element_description, county_name=None, step_name=None):
    """
    When an XPath stops working, ask Ollama to find the new locator.
    Returns an XPath string or None.
    """
    county_hint = ""
    if county_name:
        county_lower = county_name.lower()
        county_hint = f"\nSITE: {COUNTY_CONTEXT.get(county_lower, county_name)}"

    step_hint = ""
    if step_name:
        step_hint = f"\nSTEP CONTEXT: {STEP_DESCRIPTIONS.get(step_name, step_name)}"

    prompt = f"""You are helping fix a broken XPath locator for a web scraper.{county_hint}{step_hint}

ELEMENT I'M LOOKING FOR: {element_description}

PAGE HTML (trimmed to 3000 chars):
{page_html[:3000]}

Give me a single XPath expression that would locate this element in the HTML above.
Prefer locating by visible text, aria-label, name, or stable ID over positional paths.
Reply with only the XPath string, nothing else. No explanation, no markdown, no quotes."""

    answer = ask_ollama(prompt, timeout=30)
    if not answer:
        return None

    # Clean up common model artifacts
    answer = answer.strip().strip('"').strip("'").strip()
    if answer.startswith("/") or answer.startswith("("):
        return answer
    # Sometimes model returns "xpath: //..."
    if "xpath" in answer.lower() and "//" in answer:
        answer = answer[answer.index("//"):]
        return answer
    return None