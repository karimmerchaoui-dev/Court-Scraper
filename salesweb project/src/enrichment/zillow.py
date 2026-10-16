"""
Zillow Enrichment
Fetches zestimate and property metadata via the Apify Zillow actor.
"""

# ---------------------------------------------------------------------------
# API key pool — rotate randomly to spread rate-limit pressure
# ---------------------------------------------------------------------------
import os
import traceback

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()
APIFY_API_KEY = os.getenv("APIFY_API_KEY")


def get_zillow_infos(address,files_dir, max_attempts=3):
    lowest_zest=None
    for attempt in range(max_attempts):
        print(f"Attempt {attempt + 1}/{max_attempts}")

        try:
            client = ApifyClient(APIFY_API_KEY)

            run = client.actor("ENK9p4RZHg0iVso52").call(
                run_input={"addresses": [address]},
                logger=None
            )

            for item in client.dataset(run["defaultDatasetId"]).iterate_items():

                if not item.get("isValid"):
                    return None, None, None, None, None, None
                zestimate = item.get("zestimate") or item.get("price")
                print(f"Zestimate: {zestimate}")
                status = item.get("listingStatus")
                homeType = item.get("homeType")
                city = item.get("city")
                listing_type = item.get('listingType', {})
                is_auction = listing_type.get('isForAuction')
                propertyTypeDimension = item.get("propertyTypeDimension")
                is_current_signed_in_agent_responsible = item.get(
                    "isCurrentSignedInAgentResponsible"
                )
                print(f"Zestimate: {zestimate}")
                # SUCCESS: stop everything immediately
                if zestimate:
                    

                    if item.get("zestimateLowPercent"):
                        lowest_zest = float(zestimate) - (
                            float(zestimate)
                            * float(item["zestimateLowPercent"])
                            / 100
                        )
                    else:
                        f = float(zestimate)

                    
                elif  item.get("isValid"):
                    return (
                        None,
                        status,
                        homeType,
                        city,
                        propertyTypeDimension,
                        is_current_signed_in_agent_responsible,is_auction
                    )
                return (
                        lowest_zest,
                        status,
                        homeType,
                        city,
                        propertyTypeDimension,
                        is_current_signed_in_agent_responsible,is_auction
                    )
        except Exception:
            traceback.print_exc()
            continue

        print("No valid data found. Retrying...")

    return None, None, None, None, None, None,None