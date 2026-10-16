"""
Patches nj_precheck.py, nj_deed.py, nj_obituary.py, and supabase_service.py
to instrument each API call with ctx.tracker.track_step().
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  nj_precheck.py  —  Zillow + SalesWeb address + financial obligations
# ═══════════════════════════════════════════════════════════════════════════════
path_precheck = r'c:\Users\pc\PycharmProjects\Court-Scraper\pipeline\blocks\nj_precheck.py'
content = open(path_precheck, 'r', encoding='utf-8').read()

old_calls = (
    '            # \u2500\u2500 Zillow \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '            zest, status, home_type, city, prop_type, is_agent, is_auction = (\n'
    '                _fetch_zillow(address, files_dir)\n'
    '            )\n'
    '            precheck = {\n'
    '                "zestimate":  zest,\n'
    '                "zillow_status": "AUCTION" if is_auction else status,\n'
    '                "home_type":  home_type,\n'
    '            }\n'
    '\n'
    '            # \u2500\u2500 SalesWeb \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '            try:\n'
    '                county_clean = county.split("County")[0].strip()\n'
    '                sw = extract_info_from_salesweb(address, county_clean, "NJ")\n'
    '                if sw:\n'
    '                    precheck["salesweb"] = sw\n'
    '                    # Persist data to report_cases so downstream blocks can use it\n'
    '                    financial_obligations = sw.get("financial_obligations") or []\n'
    '                    unpaid_amounts = [\n'
    '                        safe_int(o.get("amount"))\n'
    '                        for o in financial_obligations\n'
    '                        if isinstance(o, dict) and o.get("category") == "unpaid_amount"\n'
    '                    ]\n'
    '                    valid_amounts = [x for x in unpaid_amounts if x is not None]\n'
    '                    precheck["unpaid_balance"] = max(valid_amounts) if valid_amounts else None\n'
    '            except Exception as sw_exc:\n'
    '                traceback.print_exc()\n'
    '                log_message(f"\u26a0\ufe0f [{case_id}] SalesWeb error (non-fatal): {sw_exc}")\n'
)

new_calls = (
    '            # \u2500\u2500 Zillow \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '            _tracker = getattr(ctx, "tracker", None)\n'
    '            _zillow_ctx = _tracker.track_step("zillow", "fetch_property_estimate") if _tracker else None\n'
    '            if _zillow_ctx:\n'
    '                _zillow_ctx.__enter__()\n'
    '            try:\n'
    '                zest, status, home_type, city, prop_type, is_agent, is_auction = (\n'
    '                    _fetch_zillow(address, files_dir)\n'
    '                )\n'
    '                if _zillow_ctx:\n'
    '                    _zillow_ctx.set_metadata("zestimate", zest)\n'
    '                    _zillow_ctx.set_metadata("listing_status", status)\n'
    '                    _zillow_ctx.set_metadata("is_auction", is_auction)\n'
    '                    _zillow_ctx.__exit__(None, None, None)\n'
    '            except Exception as _zillow_exc:\n'
    '                if _zillow_ctx:\n'
    '                    import sys as _sys\n'
    '                    _zillow_ctx.__exit__(*_sys.exc_info())\n'
    '                raise\n'
    '            precheck = {\n'
    '                "zestimate":  zest,\n'
    '                "zillow_status": "AUCTION" if is_auction else status,\n'
    '                "home_type":  home_type,\n'
    '            }\n'
    '\n'
    '            # \u2500\u2500 SalesWeb \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '            _sw_ctx = _tracker.track_step("salesweb", "matching_address") if _tracker else None\n'
    '            if _sw_ctx:\n'
    '                _sw_ctx.__enter__()\n'
    '            try:\n'
    '                county_clean = county.split("County")[0].strip()\n'
    '                sw = extract_info_from_salesweb(address, county_clean, "NJ")\n'
    '                if _sw_ctx:\n'
    '                    _sw_ctx.set_metadata("address_queried", address)\n'
    '                    _sw_ctx.set_metadata("matched", bool(sw))\n'
    '                    _sw_ctx.set_metadata("sales_web_address", sw.get("sales_web_address") if sw else None)\n'
    '                    _sw_ctx.__exit__(None, None, None)\n'
    '                if sw:\n'
    '                    precheck["salesweb"] = sw\n'
    '                    # \u2500\u2500 SalesWeb: financial obligations sub-step \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '                    _fin_ctx = _tracker.track_step("salesweb", "extract_financial_obligations") if _tracker else None\n'
    '                    if _fin_ctx:\n'
    '                        _fin_ctx.__enter__()\n'
    '                    try:\n'
    '                        financial_obligations = sw.get("financial_obligations") or []\n'
    '                        unpaid_amounts = [\n'
    '                            safe_int(o.get("amount"))\n'
    '                            for o in financial_obligations\n'
    '                            if isinstance(o, dict) and o.get("category") == "unpaid_amount"\n'
    '                        ]\n'
    '                        valid_amounts = [x for x in unpaid_amounts if x is not None]\n'
    '                        precheck["unpaid_balance"] = max(valid_amounts) if valid_amounts else None\n'
    '                        if _fin_ctx:\n'
    '                            _fin_ctx.set_metadata("obligations_count", len(financial_obligations))\n'
    '                            _fin_ctx.set_metadata("unpaid_balance", precheck["unpaid_balance"])\n'
    '                            _fin_ctx.set_metadata("approx_judgment", sw.get("approx_judgment"))\n'
    '                            _fin_ctx.__exit__(None, None, None)\n'
    '                    except Exception as _fin_exc:\n'
    '                        if _fin_ctx:\n'
    '                            import sys as _sys2\n'
    '                            _fin_ctx.__exit__(*_sys2.exc_info())\n'
    '                        log_message(f"\u26a0\ufe0f [{case_id}] SalesWeb financial obligations error (non-fatal): {_fin_exc}")\n'
    '            except Exception as sw_exc:\n'
    '                if _sw_ctx:\n'
    '                    import sys as _sys3\n'
    '                    _sw_ctx.__exit__(*_sys3.exc_info())\n'
    '                traceback.print_exc()\n'
    '                log_message(f"\u26a0\ufe0f [{case_id}] SalesWeb error (non-fatal): {sw_exc}")\n'
)

if old_calls in content:
    content = content.replace(old_calls, new_calls, 1)
    print('nj_precheck.py: Zillow+SalesWeb patched OK')
else:
    print('nj_precheck.py: anchor NOT found')

open(path_precheck, 'w', encoding='utf-8').write(content)

# ═══════════════════════════════════════════════════════════════════════════════
# 2.  nj_deed.py  —  Deed dispatch step
# ═══════════════════════════════════════════════════════════════════════════════
path_deed = r'c:\Users\pc\PycharmProjects\Court-Scraper\pipeline\blocks\nj_deed.py'
content = open(path_deed, 'r', encoding='utf-8').read()

old_deed_log = (
    '        log_message(\n'
    '            f"\U0001f4dc [{case_id}] Deed job submitted "\n'
    '            f"({\'Celery\' if _dispatched_via_celery else \'legacy queue\'}) \u2014 "\n'
    '            f"county={county_name}  book={book}  page={page}"\n'
    '        )\n'
    '\n'
    '        # Return immediately \u2014 pipeline does NOT wait for deed completion\n'
    '        return BlockSignal.OK\n'
)

new_deed_log = (
    '        log_message(\n'
    '            f"\U0001f4dc [{case_id}] Deed job submitted "\n'
    '            f"({\'Celery\' if _dispatched_via_celery else \'legacy queue\'}) \u2014 "\n'
    '            f"county={county_name}  book={book}  page={page}"\n'
    '        )\n'
    '\n'
    '        # \u2500\u2500 Track deed dispatch \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '        _tracker = getattr(ctx, "tracker", None)\n'
    '        if _tracker:\n'
    '            try:\n'
    '                with _tracker.track_step("deed", "dispatch_search_job") as _deed_step:\n'
    '                    _deed_step.set_metadata("book", book)\n'
    '                    _deed_step.set_metadata("page", page)\n'
    '                    _deed_step.set_metadata("county", county_name)\n'
    '                    _deed_step.set_metadata("main_defendant", main_defendant)\n'
    '                    _deed_step.set_metadata("dispatched_via", "celery" if _dispatched_via_celery else "legacy_queue")\n'
    '            except Exception:\n'
    '                pass  # Tracker errors must never block the pipeline\n'
    '\n'
    '        # Return immediately \u2014 pipeline does NOT wait for deed completion\n'
    '        return BlockSignal.OK\n'
)

if old_deed_log in content:
    content = content.replace(old_deed_log, new_deed_log, 1)
    print('nj_deed.py: deed dispatch tracking patched OK')
else:
    print('nj_deed.py: anchor NOT found')

open(path_deed, 'w', encoding='utf-8').write(content)

# ═══════════════════════════════════════════════════════════════════════════════
# 3.  nj_obituary.py  —  Obituary dispatch step
# ═══════════════════════════════════════════════════════════════════════════════
path_obit = r'c:\Users\pc\PycharmProjects\Court-Scraper\pipeline\blocks\nj_obituary.py'
content = open(path_obit, 'r', encoding='utf-8').read()

old_obit_dispatch = (
    '        log_message(\n'
    '            f"\U0001f4f0 [{case_id}] Obituary search dispatched via "\n'
    '            f"({\'Celery\' if _dispatched_via_celery else \'background thread\'}) "\n'
    '            f"({len(deceased_list)} person(s))"\n'
    '        )\n'
    '\n'
    '        # Return immediately \u2014 pipeline does NOT wait for this task\n'
    '        return BlockSignal.OK\n'
)

new_obit_dispatch = (
    '        log_message(\n'
    '            f"\U0001f4f0 [{case_id}] Obituary search dispatched via "\n'
    '            f"({\'Celery\' if _dispatched_via_celery else \'background thread\'}) "\n'
    '            f"({len(deceased_list)} person(s))"\n'
    '        )\n'
    '\n'
    '        # \u2500\u2500 Track obituary dispatch \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '        _tracker = getattr(ctx, "tracker", None)\n'
    '        if _tracker:\n'
    '            try:\n'
    '                with _tracker.track_step("obituary", "dispatch_search") as _obit_step:\n'
    '                    _obit_step.set_metadata("deceased_count", len(deceased_list))\n'
    '                    _obit_step.set_metadata("names", [p.get("name") or p.get("full_name") for p in deceased_list])\n'
    '                    _obit_step.set_metadata("dispatched_via", "celery" if _dispatched_via_celery else "background_thread")\n'
    '            except Exception:\n'
    '                pass  # Tracker errors must never block the pipeline\n'
    '\n'
    '        # Return immediately \u2014 pipeline does NOT wait for this task\n'
    '        return BlockSignal.OK\n'
)

if old_obit_dispatch in content:
    content = content.replace(old_obit_dispatch, new_obit_dispatch, 1)
    print('nj_obituary.py: obituary dispatch tracking patched OK')
else:
    print('nj_obituary.py: anchor NOT found — check spacing around log_message')

open(path_obit, 'w', encoding='utf-8').write(content)
