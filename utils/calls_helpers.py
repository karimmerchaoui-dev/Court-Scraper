import traceback

from apify_client import ApifyClient

from config import settings
from pipeline_tracker import update_pipeline_status
from utils.map_helpers import autocomplete_address

APIFY_API_KEY = settings.apify_api_key



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


def _fetch_zillow(search_address, files_dir):
    try:
        zest, status, home_type, city, prop_type, is_agent,is_auction = get_zillow_infos(search_address, files_dir)
        if not zest:
            addr2, city2, state2, zip2, county2 = autocomplete_address(search_address)
            zest, status, home_type, city, prop_type, is_agent,is_auction = get_zillow_infos(f"{addr2},{state2}", files_dir)
    except Exception:
        update_pipeline_status("zillow", "FAILED", tb_message=traceback.format_exc())
    return zest, status, home_type, city, prop_type, is_agent,is_auction