
# Initialize the ApifyClient with your API token
from dotenv import load_dotenv

load_dotenv()
import traceback

from apify_client import ApifyClient

# List of your API keys (shuffled at start for randomness)
#ciezef@dolby.buzz
#
#
#
#
#
from config import settings
from pipeline_tracker import update_pipeline_status

APIFY_API_KEY = settings.apify_api_key



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
                print(f"item: {item}")
                if not item.get("isValid"):
                    return None, None, None, None, None, None,None
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
                    update_pipeline_status("zillow", "SUCCESS")
                    return (
                        None,
                        status,
                        homeType,
                        city,
                        propertyTypeDimension,
                        is_current_signed_in_agent_responsible,is_auction
                    )
                update_pipeline_status("zillow", "SUCCESS")
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
    update_pipeline_status("zillow", "FAILED", tb_message=traceback.format_exc())
    return None, None, None, None, None, None,None