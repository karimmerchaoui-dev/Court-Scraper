
# Initialize the ApifyClient with your API token
import os

from dotenv import load_dotenv

load_dotenv()

# List of your API keys (shuffled at start for randomness)
#ciezef@dolby.buzz
#
#
#
#
import sys

from apify_client import ApifyClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

APIFY_API_KEY = settings.apify_api_key



import traceback

import pysnooper


@pysnooper.snoop()
def get_zillow_infos(address, files_dir, max_attempts=3):
    lowest_zest = None
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
                    return None, None, None, None, None, None, None
                print(f"item : {item}")
                zestimate = item.get("zestimate") or item.get("price")
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
                        return (
                            f,
                            status,
                            homeType,
                            city,
                            propertyTypeDimension,
                            is_current_signed_in_agent_responsible, is_auction
                        )


                elif item.get("isValid"):
                    return (
                        None,
                        status,
                        homeType,
                        city,
                        propertyTypeDimension,
                        is_current_signed_in_agent_responsible, is_auction
                    )
                return (
                    lowest_zest,
                    status,
                    homeType,
                    city,
                    propertyTypeDimension,
                    is_current_signed_in_agent_responsible, is_auction
                )
        except Exception:
            traceback.print_exc()
            continue

        print("No valid data found. Retrying...")

    return None, None, None, None, None, None


print(get_zillow_infos("819 Sunset Cove Dr, Sunset Cove, FL",files_dir=r"C:\Users\pc\PycharmProjects\Court-Scraper"))