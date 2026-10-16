"""
tests/test_pipeline_base.py
===========================
Unit tests for pipeline/base.py:
  - BlockStatus enum (UI state machine)
  - BlockSignal enum (control flow directives)
  - PipelineContext dataclass initialization and field defaults
  - FloridaPipelineContext dataclass
  - PipelineBlock abstract base class contract

Validates the state machine transitions and context passing integrity.
"""
from __future__ import annotations

import pytest

from pipeline.base import (
    BlockSignal,
    BlockStatus,
    FloridaPipelineContext,
    PipelineBlock,
    PipelineContext,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. BlockStatus & BlockSignal Enums
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineEnums:
    """Tests for BlockStatus and BlockSignal enums."""

    def test_block_status_has_all_lifecycle_values(self):
        expected = {"pending", "running", "success", "failed", "retrying", "skipped"}
        actual = {status.value for status in BlockStatus}
        assert expected == actual

    def test_block_signal_has_all_routing_directives(self):
        expected = {
            "ok",
            "retry_driver",
            "retry_from_start",
            "retry_from_nav",
            "retry_from_row",
            "not_found",
            "skip",
            "stop",
        }
        actual = {signal.value for signal in BlockSignal}
        assert expected == actual

    def test_block_signal_str_compatibility(self):
        """BlockSignal inherits from str, so it supports string equality."""
        assert BlockSignal.OK == "ok"
        assert BlockSignal.SKIP == "skip"
        assert BlockSignal.STOP == "stop"


# ══════════════════════════════════════════════════════════════════════════════
# 2. PipelineContext & FloridaPipelineContext
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineContexts:
    """Tests for state container dataclasses."""

    def test_pipeline_context_initialization_with_defaults(self):
        ctx = PipelineContext(
            case_id="f-1234-24",
            year="24",
            docket="1234",
            case_type="foreclosure",
            account={"user": "test_user"},
            driver=None,
            driver_pool=None,
            files_dir="/dummy/dir",
        )

        assert ctx.case_id == "f-1234-24"
        assert ctx.start_index == 0
        assert isinstance(ctx.precheck_data, dict)
        assert isinstance(ctx.case_result, dict)
        assert isinstance(ctx.matching_files, list)
        assert isinstance(ctx.matching_rows, list)
        assert ctx.row_index_to_retry is None
        assert ctx.start_time > 0

    def test_florida_pipeline_context_initialization(self):
        fl_ctx = FloridaPipelineContext(
            case_id="2023-CA-001234",
            config={"login_url": "https://court.example.com"},
            driver=None,
            driver_pool=None,
            files_dir="/dummy/dir",
        )

        assert fl_ctx.case_id == "2023-CA-001234"
        assert fl_ctx.config["login_url"] == "https://court.example.com"
        assert fl_ctx.cached_matching_rows is None
        assert fl_ctx.down_flag is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. PipelineBlock ABC Contract
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineBlockContract:
    """Tests for the PipelineBlock abstract base class."""

    def test_cannot_instantiate_abstract_block_directly(self):
        with pytest.raises(TypeError):
            PipelineBlock(name="Abstract")  # type: ignore

    def test_concrete_block_must_implement_execute(self):
        class DummySuccessBlock(PipelineBlock):
            def execute(self, ctx: PipelineContext) -> BlockSignal:
                return BlockSignal.OK

        block = DummySuccessBlock(name="DummyBlock")
        assert block.name == "DummyBlock"
        assert repr(block) == "<Block: DummyBlock>"

        ctx = PipelineContext(
            case_id="f-1",
            year="24",
            docket="1",
            case_type="CA",
            account={},
            driver=None,
            driver_pool=None,
            files_dir="/tmp",
        )

        signal = block.execute(ctx)
        assert signal == BlockSignal.OK
