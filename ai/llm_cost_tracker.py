"""
llm_cost_tracker.py
Tracks token usage, API calls, and estimated USD costs for each task:
  - complaint (extract_complaint)
  - judgment (extract_final_judgment)
  - bankruptcy (get_bankruptcy_case_status)
  - deed (deed search address match & extraction)
  - obituary (obituary search & extraction)
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

# Standard pricing in USD per 1,000,000 tokens (Input, Output)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    # Groq
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.3-70b": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "llama-3.1-8b": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    # Google Gemini
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-exp": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    # Mistral
    "mistral-small": {"input": 0.20, "output": 0.60},
    "mistral-large": {"input": 2.00, "output": 6.00},
    # Fallback default
    "default": {"input": 0.20, "output": 0.80},
}

COST_FILE = Path(__file__).parent / "llm_costs.json"
_lock = threading.Lock()

DEFAULT_TASKS = ["complaint", "judgment", "bankruptcy", "deed", "obituary"]

def _init_stats() -> Dict[str, Any]:
    stats = {}
    for task in DEFAULT_TASKS:
        stats[task] = {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost": 0.0,
            "last_model": "",
            "last_service": "",
        }
    return stats

_stats: Dict[str, Any] = _init_stats()

def _load_stats():
    global _stats
    if COST_FILE.exists():
        try:
            with open(COST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k in DEFAULT_TASKS:
                        if k in data and isinstance(data[k], dict):
                            _stats[k].update(data[k])
        except Exception as e:
            print(f"[LLM Cost] Error loading {COST_FILE}: {e}")

_load_stats()

def _save_stats():
    try:
        with open(COST_FILE, "w", encoding="utf-8") as f:
            json.dump(_stats, f, indent=2)
    except Exception as e:
        print(f"[LLM Cost] Error saving {COST_FILE}: {e}")

def get_pricing_for_model(model_name: str) -> Dict[str, float]:
    if not model_name:
        return MODEL_PRICING["default"]
    mdl = model_name.lower().strip()
    for pattern, rates in MODEL_PRICING.items():
        if pattern in mdl:
            return rates
    return MODEL_PRICING["default"]

def record_llm_cost(
    task: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    service: str = "",
    explicit_cost: Optional[float] = None,
) -> float:
    """Record an LLM invocation's token usage and cost for a given task."""
    task_key = task.lower().strip()
    if task_key not in _stats:
        task_key = "complaint"  # fallback

    try:
        t_in = int(tokens_in or 0)
    except (ValueError, TypeError):
        t_in = 0

    try:
        t_out = int(tokens_out or 0)
    except (ValueError, TypeError):
        t_out = 0

    rates = get_pricing_for_model(model)
    if explicit_cost is not None:
        call_cost = float(explicit_cost)
    else:
        call_cost = ((t_in * rates["input"]) + (t_out * rates["output"])) / 1_000_000.0

    with _lock:
        st = _stats[task_key]
        st["calls"] += 1
        st["tokens_in"] += t_in
        st["tokens_out"] += t_out
        st["cost"] = round(st["cost"] + call_cost, 6)
        if model:
            st["last_model"] = str(model)
        if service:
            st["last_service"] = str(service)
        _save_stats()

    # Attempt to broadcast live update via socketio if available
    try:
        from app import socketio
        summary = get_cost_summary()
        socketio.emit("llm_costs_updated", summary)
    except Exception:
        pass

    return call_cost

def get_cost_summary() -> Dict[str, Any]:
    with _lock:
        tasks_summary = {}
        total_calls = 0
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost = 0.0

        for task, data in _stats.items():
            t_in = data.get("tokens_in", 0)
            t_out = data.get("tokens_out", 0)
            c = data.get("cost", 0.0)
            tasks_summary[task] = {
                **data,
                "calls": data.get("calls", 0),
                "tokens_in": t_in,
                "tokens_out": t_out,
                "prompt_tokens": t_in,
                "completion_tokens": t_out,
                "total_tokens": t_in + t_out,
                "cost": c,
                "cost_usd": c,
            }
            total_calls += data.get("calls", 0)
            total_tokens_in += t_in
            total_tokens_out += t_out
            total_cost += c

        rounded_cost = round(total_cost, 6)
        return {
            "tasks": tasks_summary,
            "by_task": tasks_summary,
            "total_calls": total_calls,
            "total_tokens_in": total_tokens_in,
            "total_prompt_tokens": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_completion_tokens": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "total_cost": rounded_cost,
            "total_cost_usd": rounded_cost,
            "formatted_total_cost": f"${total_cost:.4f}",
        }

def reset_llm_costs():
    global _stats
    with _lock:
        _stats = _init_stats()
        _save_stats()
    try:
        from app import socketio
        socketio.emit("llm_costs_updated", get_cost_summary())
    except Exception:
        pass
    return get_cost_summary()
