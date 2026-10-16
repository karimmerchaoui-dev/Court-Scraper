
import traceback
from base64 import b64decode
from typing import Any, Dict, List, Optional

import pysnooper
import requests
from bs4 import BeautifulSoup

from ai.llm_helper import get_obituary_link_data
from pipeline_tracker import update_pipeline_status


@pysnooper.snoop()
def search_obituaries(first_name: str, last_name: str, state: str, 

                      base_url: str = "http://localhost:8101",
                      api_key: Optional[str] = None,
                      timeout: int = 120) -> List[Dict[str, Any]]:
    """
    Search for obituaries and return a list of dictionaries.
    
    Args:
        first_name: Person's first name
        last_name: Person's last name
        state: US state (e.g., "NJ", "New Jersey", "Jersey")
        base_url: API server URL
        api_key: Optional API key for authentication
        timeout: Request timeout in seconds
    
    Returns:
        List of dictionaries, each containing obituary data
    
    Raises:
        Exception: If the request fails
    """
    try:
        # Build the request
        url = f"{base_url.rstrip('/')}/obituaries/search"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "state": state
        }
        
        # Make the request
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        
        # Check for errors
        if response.status_code == 400:
            raise Exception(f"Bad request: {response.json().get('detail', 'unknown')}")
        if response.status_code == 401:
            raise Exception("Unauthorized - check your API key")
        if response.status_code == 502:
            raise Exception(f"Scraping failed: {response.json().get('detail', 'unknown')}")
        
        response.raise_for_status()
        
        # Return the results as a list of dicts
        data = response.json()
        return data.get("results", [])
    except Exception as e:
        update_pipeline_status("obituary", "FAILED", tb_message=traceback.format_exc())
        return []


# Headers stay constant across calls

HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.5',
    'cache-control': 'max-age=0',
    'if-modified-since': 'Fri, 19 Jun 2026 08:43:29 GMT',
    'priority': 'u=0, i',
    'sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-full-version-list': '"Brave";v="149.0.0.0", "Chromium";v="149.0.0.0", "Not)A;Brand";v="24.0.0.0"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"19.0.0"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'sec-gpc': '1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    # 'cookie': 'ppid=1b6fccc5-2f38-491d-8d82-6d5a7d345677; statsig_stable_id=2a0ffff8-8771-41b5-99fe-ce55ef6a7d85; engagement_popup_dismissed=%7B%22dismissed%22%3Atrue%2C%22at%22%3A1781698592626%7D; csrftoken=xiOkk6heeAAHYbPCcoCN0FptXcGGIit0; cf_clearance=JhQvuJUS5dCuQmx7uvfza2Ebxi43ie1u7mCdeaSlvdY-1781777059-1.2.1.1-eh9NXe41FAkzx3457tQq3NG1NrfaO4dDVTUOz87njAP6sNlpsLVHBjAY_2QJnSosBpDKWPUH1U5KHmJNMK78CaVb4zkWlydssitU5AhyOcha_u5SyCeLGd2VvKBz3qI150LuPYVQ0Hi09wvST3e8uoFEbrZkxgnjHVQ2Uy9eIwbqLjejXXnmAiGyrsJCy_uL1hQCkqgrCrjk3jLa7aOUu2kiNwb8wc8A.7fkydb84K9YrGMn32N9d_LSp6n24mH9sHpGeR7Z6Sj3IEjGrq6CiXXBmtykGFgcLuF9n0fv7guriH0fwPwilZa.Vw_RoTd8JwBhuwxgPJ8fFuHpnKb7X73fy0DLN86uaAzCAeLzThbGsUIkYavfZwiBdtg4aDO9tuvwUmtKDHB_Ntyq7yx3YFkcul5VVb5iEeX30VypJDvdAGuVdYW2g.EItOA.dBr33oJV0ucEf33GRkcEPWdPE4KYBO7R8wIzn11uKqx44Zr3jKyUMTIvopelWCX4p88s6An.PzI3M2zfGKk4uubYuw; allowRefreshAd=',
}

def get_obituary_paragraphs(link, publication: str = "courierpostonline"):
    """
    Fetch the ObituaryParagraph text elements from a legacy.com obituary page.

    Args:
        name: URL slug for the obituary, e.g. "gertrude-downing-obituary"
              (the part after ".../name/")
        obit_id: the obituary's numeric id, sent as the 'id' query param
        cookies: dict of cookies to send with the request
        publication: publication slug in the URL path, e.g. "courierpostonline"
                     (defaults to "courierpostonline" since that's what your
                     original example used)

    Returns:
        list[str]: text of each <... data-component="ObituaryParagraph"> element
    """
    api_response = requests.post(
    "https://api.zyte.com/v1/extract",
    auth=("63a11ffcd4d947dc9b36af1b38e6e631", ""),  # Your API key goes in place of the dots
    json={
        "url": link,
        "httpResponseBody": True,
        "followRedirect": True,
    },
    )
    html_content: bytes = b64decode(
        api_response.json()["httpResponseBody"])
    soup = BeautifulSoup(html_content, "html.parser")
    elements = soup.find_all(attrs={"data-component": "ObituaryParagraph"})
    return elements




def process_obituary_link(link,publication: str = "courierpostonline"):


    elements = get_obituary_paragraphs(link, publication)
    if elements:
        obituary_text = "\n".join(el.get_text(strip=True) for el in elements)
        return get_obituary_link_data(obituary_text)
    else:
        return
