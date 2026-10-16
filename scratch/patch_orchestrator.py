path = r'c:\Users\pc\PycharmProjects\Court-Scraper\pipeline\orchestrator.py'
content = open(path, 'r', encoding='utf-8').read()

# ── 1. Add import at top (after existing imports block) ──────────────────
old_import = 'from app import log_message\nimport pysnooper'
new_import = (
    'from app import log_message\n'
    'import pysnooper\n'
    'from pipeline_tracker import PipelineTracker\n'
    'from database.supabase_service import supabase as _supabase_client\n'
)
if old_import in content:
    content = content.replace(old_import, new_import, 1)
    print('Import injection OK')
else:
    print('Import anchor NOT found')

# ── 2. Inject tracker start right after "Initialise all blocks as PENDING" loop ──
old_init = (
    '        # Initialise all blocks as PENDING in the UI\n'
    '        for block in self.blocks:\n'
    '            self._emit(ctx, block, BlockStatus.PENDING)\n'
    '\n'
    '        driver_retries = 0\n'
)
new_init = (
    '        # Initialise all blocks as PENDING in the UI\n'
    '        for block in self.blocks:\n'
    '            self._emit(ctx, block, BlockStatus.PENDING)\n'
    '\n'
    '        # \u2500\u2500 Start tracker run \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '        if ctx.tracker is None:\n'
    '            try:\n'
    '                ctx.tracker = PipelineTracker(\n'
    '                    supabase_client=_supabase_client,\n'
    '                    case_number=ctx.case_id,\n'
    '                    batch_name=getattr(ctx, "batch_name", ""),\n'
    '                )\n'
    '                ctx.tracker.start_run()\n'
    '            except Exception as _te:\n'
    '                log_message(f"\u26a0\ufe0f [{ctx.case_id}] Tracker init failed (non-fatal): {_te}")\n'
    '                ctx.tracker = None\n'
    '        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '\n'
    '        driver_retries = 0\n'
)
if old_init in content:
    content = content.replace(old_init, new_init, 1)
    print('Tracker start injection OK')
else:
    print('Tracker start anchor NOT found')

# ── 3. Complete run on SUCCESS ─────────────────────────────────────────────
old_success = '        return SearchResult.SUCCESS\n'
new_success = (
    '        # \u2500\u2500 All blocks completed — mark run as COMPLETED \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '        if getattr(ctx, "tracker", None):\n'
    '            try:\n'
    '                ctx.tracker.complete_run(success=True)\n'
    '            except Exception:\n'
    '                pass\n'
    '        return SearchResult.SUCCESS\n'
)
if old_success in content:
    content = content.replace(old_success, new_success, 1)
    print('Tracker complete (SUCCESS) injection OK')
else:
    print('SUCCESS anchor NOT found')

# ── 4. Complete run on NOT_FOUND / SKIP ─────────────────────────────────
old_not_found = (
    '            elif signal in (BlockSignal.NOT_FOUND, BlockSignal.SKIP):\n'
    '                self._emit(ctx, block, BlockStatus.SKIPPED)\n'
    '                self._skip_remaining(ctx, i + 1)\n'
    '                self._release_driver(ctx)\n'
    '                return SearchResult.NOT_FOUND\n'
)
new_not_found = (
    '            elif signal in (BlockSignal.NOT_FOUND, BlockSignal.SKIP):\n'
    '                self._emit(ctx, block, BlockStatus.SKIPPED)\n'
    '                self._skip_remaining(ctx, i + 1)\n'
    '                self._release_driver(ctx)\n'
    '                if getattr(ctx, "tracker", None):\n'
    '                    try:\n'
    '                        ctx.tracker.complete_run(success=False)\n'
    '                    except Exception:\n'
    '                        pass\n'
    '                return SearchResult.NOT_FOUND\n'
)
if old_not_found in content:
    content = content.replace(old_not_found, new_not_found, 1)
    print('Tracker complete (NOT_FOUND) injection OK')
else:
    print('NOT_FOUND anchor NOT found')

# ── 5. Complete run on STOP signal ─────────────────────────────────────
old_stop = (
    '            elif signal == BlockSignal.STOP:\n'
    '                self._emit(ctx, block, BlockStatus.FAILED)\n'
    '                self._skip_remaining(ctx, i + 1)\n'
    '                self._release_driver(ctx)\n'
    '                return SearchResult.ERROR\n'
)
new_stop = (
    '            elif signal == BlockSignal.STOP:\n'
    '                self._emit(ctx, block, BlockStatus.FAILED)\n'
    '                self._skip_remaining(ctx, i + 1)\n'
    '                self._release_driver(ctx)\n'
    '                if getattr(ctx, "tracker", None):\n'
    '                    try:\n'
    '                        ctx.tracker.complete_run(success=False)\n'
    '                    except Exception:\n'
    '                        pass\n'
    '                return SearchResult.ERROR\n'
)
if old_stop in content:
    content = content.replace(old_stop, new_stop, 1)
    print('Tracker complete (STOP) injection OK')
else:
    print('STOP anchor NOT found')

# ── 6. Complete run on unexpected exception ───────────────────────────
old_unexp = (
    '            except Exception as exc:\n'
    '                exc_desc = f"Unexpected error in block [{block.name}]: {type(exc).__name__} ({exc})"\n'
    '                ctx.last_failed_block = block.name\n'
    '                ctx.retry_reason = exc_desc\n'
    '                self._emit(ctx, block, BlockStatus.FAILED, reason=exc_desc)\n'
    '                _log_unexpected_error(ctx, block, exc)\n'
    '                traceback.print_exc()\n'
    '                return SearchResult.ERROR\n'
)
new_unexp = (
    '            except Exception as exc:\n'
    '                exc_desc = f"Unexpected error in block [{block.name}]: {type(exc).__name__} ({exc})"\n'
    '                ctx.last_failed_block = block.name\n'
    '                ctx.retry_reason = exc_desc\n'
    '                self._emit(ctx, block, BlockStatus.FAILED, reason=exc_desc)\n'
    '                _log_unexpected_error(ctx, block, exc)\n'
    '                traceback.print_exc()\n'
    '                if getattr(ctx, "tracker", None):\n'
    '                    try:\n'
    '                        ctx.tracker.complete_run(success=False)\n'
    '                    except Exception:\n'
    '                        pass\n'
    '                return SearchResult.ERROR\n'
)
if old_unexp in content:
    content = content.replace(old_unexp, new_unexp, 1)
    print('Tracker complete (unexpected exc) injection OK')
else:
    print('Unexpected exc anchor NOT found')

# ── 7. Complete run on max driver retries safety valve ───────────────
old_maxretry = (
    '            if driver_retries >= _MAX_DRIVER_RETRIES:\n'
    '                # Safety valve \u2014 don\'t loop forever\n'
    '                self._skip_remaining(ctx, i + 1)\n'
    '                self._release_driver(ctx)\n'
    '                return SearchResult.ERROR\n'
)
new_maxretry = (
    '            if driver_retries >= _MAX_DRIVER_RETRIES:\n'
    '                # Safety valve \u2014 don\'t loop forever\n'
    '                self._skip_remaining(ctx, i + 1)\n'
    '                self._release_driver(ctx)\n'
    '                if getattr(ctx, "tracker", None):\n'
    '                    try:\n'
    '                        ctx.tracker.complete_run(success=False)\n'
    '                    except Exception:\n'
    '                        pass\n'
    '                return SearchResult.ERROR\n'
)
if old_maxretry in content:
    content = content.replace(old_maxretry, new_maxretry, 1)
    print('Tracker complete (max retries) injection OK')
else:
    print('Max retries anchor NOT found')

open(path, 'w', encoding='utf-8').write(content)
print('Done. Total lines:', content.count('\n'))
