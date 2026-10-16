# Initialize the ApifyClient with your Apify API token
# Replace '<YOUR_API_TOKEN>' with your token.
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()
# List of your API keys
import traceback

from config import settings
from pipeline_tracker import update_pipeline_status


def defendant_skip_trace(name, address):

    # Try each API key until one works
    try:
        client = ApifyClient(settings.apify_api_key)

        # Prepare the Actor input
        run_input = {
            "name": [f"{name}; {address}"]
        }

        # Run the Actor and wait for it to finish
        run = client.actor("one-api/skip-trace").call(run_input=run_input)

        dataset_id = run["defaultDatasetId"]

        print(
            "💾 Check your data here: "
            f"https://console.apify.com/storage/datasets/{dataset_id}"
        )

        # Get dataset info (contains item count)
        dataset_info = client.dataset(dataset_id).get()
        item_count = dataset_info.get("itemCount", 0)
        print("Total items:", item_count)

        # Get first item
        items = list(client.dataset(dataset_id).iterate_items())

        if items:
            first_item = items[0]
            print("First item:")
            return first_item
        else:
            print("No items found.")
            return None
            
    except Exception as e:
        update_pipeline_status("deed", "FAILED", tb_message=traceback.format_exc())
        
    
    print("❌ All API keys failed for skip-trace!")
    return None
