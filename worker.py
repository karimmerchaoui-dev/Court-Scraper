import json
import sys

from utils.obituary_helpers import process_obituary_link

link = sys.argv[1]
cookies = {
    'cf_clearance': 'vALMxqFQmCOCzQtT0VkLzfc7oEXnZNE3EqBLzq26aYc-1782376646-1.2.1.1-JBYr9FR0p_54dImnPUxsSo2YkKafJvKwenrA.ukVGd7Se5PSVJ6lF.w12hJyAFy6rsc3SV_Cxgx8t8dmi9SFS0MJUfIEesjUs729JL5h9aNdl_FBmiVYxQe4dvOoEcfYe2qadddnCTqvE3ipNosrtYoGxXoDlGkesYxHy0Bm9qfRtjf7H7E7QQW4u.KA4xO1yQoiVGjdE1tYCsnZbX8nuksQt4nyh1JqNjbbA2Rz9EY4MujhFHyJEJiWobK5O59XNw0r7x4CVsidtU5mPBnI5npI5_Ynlq44EBCkqRGR.GB7LtS.3niUIr46J24cg0QCn_WbYfzhVWea9RDXqKrEmAwUA53yIe2ia5L2W3RQcIrafhrDFSVyTtYcxFwLsyBGDDT3J98iLPAMgyn.fA3Ugx6uNV5IiSn7b1iLUbRTf8smTeB1an.agWSJzu_a_2iapvkRtlfskej1x3xlmCL5Zid_ycU.9t5AXporwhGmspScmF9ISmyJjpF7ou6MKSrE74ZSYBAnwpiBONnF6vs0qg',
    'allowRefreshAd': '',
    'ppid': 'bf6bf892-189c-45b3-81e0-159167251fad',
    'engagement_popup_dismissed': '%7B%22dismissed%22%3Atrue%2C%22at%22%3A1782378260154%7D',
}

result = process_obituary_link(link, cookies)

print(json.dumps(result))