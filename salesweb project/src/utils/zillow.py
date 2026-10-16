"""
Zillow property data retrieval via Apify.
API keys are rotated randomly to distribute load.
"""

import os
import traceback

from apify_client import ApifyClient

APIFY_API_KEY = os.getenv("APIFY_API_KEY")


def get_zillow_infos(address: str, files_dir: str, max_attempts: int = 3):
    """
    Fetch Zillow property info for a given address using Apify.

    Returns:
        Tuple of (lowest_zestimate, status, home_type, city,
                  property_type_dimension, is_current_signed_in_agent_responsible)
        All values are None on failure.
    """

    print(f"Zillow lookup — {address}")
    try:
        client = ApifyClient(APIFY_API_KEY)
        run = client.actor("ENK9p4RZHg0iVso52").call(
            run_input={"addresses": [address]},
            logger=None,
        )
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if not item.get("isValid"):
                return None, None, None, None, None, None,None

            zestimate = item.get("zestimate") or item.get("price")
            print(f"Zestimate: {zestimate}")
            status = item.get("listingStatus")
            home_type = item.get("homeType")
            city = item.get("city")
            prop_type_dim = item.get("propertyTypeDimension")
            is_agent = item.get("isCurrentSignedInAgentResponsible")
            listing_type = item.get('listingType', {})
            is_auction = listing_type.get('isForAuction')

            if is_auction:
                status = "AUCTION"
            lowest_zest = None
            if zestimate:
                z = float(zestimate)
                low_pct = item.get("zestimateLowPercent")
                lowest_zest = z - (z * float(low_pct) / 100) if low_pct else z

            return lowest_zest, status, home_type, city, prop_type_dim, is_agent,is_auction

    except Exception:
        traceback.print_exc()

    return None, None, None, None, None, None,None
