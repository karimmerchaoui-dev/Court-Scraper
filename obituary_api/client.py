"""
Simple Obituary API Client
==========================
Makes a request to the obituary API and returns a list of dictionaries.
"""

from typing import Any, Dict, List, Optional

import pysnooper
import requests


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


# ── Simple usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Example usage
    try:
        results = search_obituaries("GRACE", "FENTY", "NJ")
        
        print(f"Found {len(results)} result(s):\n")
        for i, result in enumerate(results, 1):
            print(f"{'─' * 60}")
            print(f"Result #{i}")
            print(f"{'─' * 60}")
            print(f"Name: {result.get('full_name')}")
            print(f"URL: {result.get('url')}")
            print(f"Birth: {result.get('birth_date')}")
            print(f"Death: {result.get('death_date')}")
            print(f"Age: {result.get('age')}")
            print(f"Bio: {result.get('bio', '')}...")
            print(f"Friends: {len(result.get('friends', []))}")
            print(f"Heirs: {len(result.get('heirs', []))}")
            print()
            
    except Exception as e:
        print(f"Error: {e}")