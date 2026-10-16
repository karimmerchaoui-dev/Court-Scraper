
from supabase import create_client

from config import settings

url = settings.supabase_url
key = settings.supabase_key

supabase = create_client(url, key)

rpc_payload = {
  "p_case_number": "f-6216-25",
  "p_batch_name": "batch_paria",
  "p_city_id_fk": "f78f5258-8b41-4ef4-b1c2-a081fe392c54",
  "p_case_payload": {
    "case_number": "f-6216-25",
    "processing_status": "new",
    "court_case_status": "Defaulted",
    "processing_duration": "348.39",
    "county": "Middlesex",
    "case_type": " Condominium Or Homeowners Association Lien Foreclosure",
    "batch_name": "batch_paria",
    "city_id": "f78f5258-8b41-4ef4-b1c2-a081fe392c54",
    "bankruptcy_case_status": "❌"
  },
  "p_def_payload": {
    "case_id": "00000000-0000-0000-0000-000000000000",
    "main_defendant": "Melissa A Bandura",
    "homeowner_deceased": None,
    "date_of_death": None
  },
  "p_loc_payload": {
    "case_id": "00000000-0000-0000-0000-000000000000",
    "court_address": "1207 Harbour Club Drive",
    "block": "451",
    "lot": "1.08"
  },
  "p_judg_payload": {
    "case_id": "00000000-0000-0000-0000-000000000000",
    "additional_sums_count": "0",
    "judgment_date": "December 4, 2025",
    "total_final_judgment_amount": "$6,558.77"
  },
  "p_mort_payload": None,
  "p_sales_payload": {
    "case_id": "00000000-0000-0000-0000-000000000000",
    "sales_web_address": None,
    "found": "✅",
    "upset_price": "$12,201.46",
    "upset_amount": None,
    "approx_judgment": "$12,201.46",
    "approx_upset": None
  },
  "p_prop_payload": {
    "case_id": "00000000-0000-0000-0000-000000000000",
    "address": "1207 Harbour Club Drive",
    "zestimate": 309504.0,
    "zillow_status": "OTHER",
    "home_type": "CONDO",
    "equity": 297303.0,
    "is_current_signed_in_agent_responsible": None
  },
  "p_parties_batch": [
    {
      "case_id": "00000000-0000-0000-0000-000000000000",
      "name": "Melissa A Bandura",
      "description": "Individual",
      "party_index": 1
    },
    {
      "case_id": "00000000-0000-0000-0000-000000000000",
      "name": "Occupants Unknown Tenants And     AKA",
      "description": None,
      "party_index": 2
    }
  ],
  "p_events_batch": [],
  "p_deceased_batch": None
}



response = supabase.rpc("upsert_unified_case_data", rpc_payload).execute()
print(response.data)
print(response)

case_id = response.data  # the UUID

verification = (
    supabase.table("cases")
    .select("id, case_number")
    .eq("id", case_id)
    .execute()
)

print("VERIFICATION:", verification.data)
"""
def push_salesweb_to_supabase(case_number: str, salesweb_data: dict, report_cases: dict = None) -> bool:

    try:
        # 1. Get the case UUID
        case_id = get_case_id_by_number(case_number)
        if not case_id:
            print(f"❌ Case '{case_number}' not found in database!")
            return False
        
        # 2. Build the sales web payload from the salesweb_data
        #    Map the exact keys from extract_info_from_salesweb to database columns
        sales_payload = {
            "case_id": case_id,
            "found": salesweb_data.get("found", ""),
            "sales_web_address": salesweb_data.get("sales_web_address", ""),
            "upset_price": salesweb_data.get("Upset Price", ""),
            "upset_amount": salesweb_data.get("Upset Amount", ""),
            "approx_judgment": salesweb_data.get("Approx. Judgment", ""),
            "approx_upset": salesweb_data.get("Approx. Upset", ""),
            "sales_date": salesweb_data.get("sales_date", None),
        }
        
        # 3. Clean up the data (remove empty strings, convert None for date)
        cleaned_payload = {}
        for key, value in sales_payload.items():
            if isinstance(value, str) and value.strip() == "":
                cleaned_payload[key] = None
            else:
                cleaned_payload[key] = value
        
        # 4. Upsert to Supabase
        result = supabase.table("case_sales_web").upsert(
            cleaned_payload,
            on_conflict="case_id"
        ).execute()
        
        print(f"✅ SalesWeb data pushed successfully for case {case_number}")
        
        # 5. If report_cases is provided, update it too (keeps your local dict in sync)
        if report_cases is not None and case_number in report_cases:
            for key in ['found', 'sales_web_address', 'Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset', 'sales_date']:
                if key in salesweb_data and salesweb_data.get(key):
                    report_cases[case_number][key] = salesweb_data.get(key, '')
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to push SalesWeb data for case {case_number}: {e}")
        return False


items = [
    "F-9747-25",
]
address="19 Hillview Drive"
county="Monmouth"
sw = extract_info_from_salesweb(address, county, 'NJ')
print(sw)
push_salesweb_to_supabase("f-8425-25", sw)"""