#!/usr/bin/env python3
"""
Ollama benchmark: per-model serial performance + parallel stress test.
Usage: python3 scripts/benchmark-ollama.py
"""

import json
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# ── Config ────────────────────────────────────────────────────────────────────

ENDPOINTS = {
    "backdraft (Tesla M10)": "http://backdraft:11434",
}

PROMPT = (
    "Explain the difference between a process and a thread in operating systems. "
    "Be concise but complete — aim for three short paragraphs."
)

PARALLEL_PROMPT = (
    "Write a haiku about parallel computing."
)

# ── Data ──────────────────────────────────────────────────────────────────────

@dataclass
class Result:
    endpoint_label: str
    model: str
    prompt_tokens: int = 0
    eval_tokens: int = 0
    prompt_tps: float = 0.0
    eval_tps: float = 0.0
    total_s: float = 0.0
    error: str = ""

@dataclass
class ParallelResult:
    model: str
    eval_tps: float = 0.0
    wall_s: float = 0.0
    start_offset_s: float = 0.0
    finish_s: float = 0.0
    error: str = ""

# ── Helpers ───────────────────────────────────────────────────────────────────

def list_models(base_url: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=10) as r:
            return [m["name"] for m in json.load(r)["models"]]
    except Exception as e:
        print(f"  [warn] could not list models at {base_url}: {e}")
        return []

def generate(base_url: str, model: str, prompt: str, timeout: int = 300) -> dict:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "seed": 42},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def run_serial(label: str, base_url: str, model: str) -> Result:
    r = Result(endpoint_label=label, model=model)
    try:
        t0 = time.perf_counter()
        data = generate(base_url, model, PROMPT)
        r.total_s = time.perf_counter() - t0
        r.eval_tokens   = data.get("eval_count", 0)
        r.prompt_tokens = data.get("prompt_eval_count", 0)
        pd = data.get("prompt_eval_duration", 1)
        ed = data.get("eval_duration", 1)
        r.prompt_tps = r.prompt_tokens / pd * 1e9 if pd else 0
        r.eval_tps   = r.eval_tokens   / ed * 1e9 if ed else 0
    except Exception as e:
        r.error = str(e)
    return r

# ── Serial benchmark ──────────────────────────────────────────────────────────

def run_serial_benchmarks() -> list[Result]:
    results = []
    for label, url in ENDPOINTS.items():
        models = list_models(url)
        if not models:
            print(f"  [skip] no models at {url}")
            continue
        print(f"\n{'─'*60}")
        print(f"Serial benchmarks — {label}")
        print(f"{'─'*60}")
        for model in models:
            print(f"  {model:<35}", end="", flush=True)
            r = run_serial(label, url, model)
            if r.error:
                print(f"  ERROR: {r.error}")
            else:
                print(f"  {r.eval_tps:5.1f} tok/s  ({r.eval_tokens} tokens, {r.total_s:.1f}s)")
            results.append(r)
    return results

# ── Parallel stress test ───────────────────────────────────────────────────────

def run_parallel_test() -> list[ParallelResult]:
    url = ENDPOINTS["backdraft (Tesla M10)"]
    models = list_models(url)
    if not models:
        return []

    # Use up to 4 models (one per physical GPU)
    test_models = models[:4]
    print(f"\n{'─'*60}")
    print(f"Parallel stress test — backdraft (Tesla M10)")
    print(f"Firing {len(test_models)} concurrent requests simultaneously")
    print(f"{'─'*60}")

    wall_start = time.perf_counter()
    futures_map = {}
    par_results = {m: ParallelResult(model=m) for m in test_models}

    with ThreadPoolExecutor(max_workers=len(test_models)) as ex:
        for model in test_models:
            futures_map[ex.submit(generate, url, model, PARALLEL_PROMPT)] = model

        for fut in as_completed(futures_map):
            model = futures_map[fut]
            finish = time.perf_counter() - wall_start
            pr = par_results[model]
            pr.finish_s = finish
            try:
                data = fut.result()
                ec = data.get("eval_count", 0)
                ed = data.get("eval_duration", 1)
                pr.eval_tps = ec / ed * 1e9 if ed else 0
                print(f"  {model:<35}  finished at +{finish:.1f}s  {pr.eval_tps:.1f} tok/s")
            except Exception as e:
                pr.error = str(e)
                print(f"  {model:<35}  ERROR: {e}")

    total_wall = time.perf_counter() - wall_start
    print(f"\n  Wall clock for all {len(test_models)} concurrent requests: {total_wall:.1f}s")
    return list(par_results.values())

# ── Report ────────────────────────────────────────────────────────────────────

def print_report(serial: list[Result], parallel: list[ParallelResult]):
    print(f"\n{'═'*70}")
    print("SERIAL BENCHMARK RESULTS")
    print(f"{'═'*70}")
    print(f"{'Endpoint':<30} {'Model':<35} {'Prompt':>8} {'Eval':>8} {'Time':>7}")
    print(f"{'':─<30} {'':─<35} {'tok/s':>8} {'tok/s':>8} {'(s)':>7}")
    for r in serial:
        if r.error:
            print(f"{r.endpoint_label:<30} {r.model:<35} {'ERROR':>8}")
        else:
            print(f"{r.endpoint_label:<30} {r.model:<35} {r.prompt_tps:>7.1f} {r.eval_tps:>7.1f} {r.total_s:>7.1f}")

    if parallel:
        print(f"\n{'═'*70}")
        print("PARALLEL STRESS TEST — backdraft (Tesla M10)")
        print(f"{'═'*70}")
        print(f"{'Model':<35} {'Eval tok/s':>12} {'Finished at':>13}")
        print(f"{'':─<35} {'':─<12} {'':─<13}")
        for pr in parallel:
            if pr.error:
                print(f"{pr.model:<35} {'ERROR':>12}")
            else:
                print(f"{pr.model:<35} {pr.eval_tps:>11.1f} {pr.finish_s:>11.1f}s")

        ok = [pr for pr in parallel if not pr.error]
        if ok:
            avg_tps = sum(pr.eval_tps for pr in ok) / len(ok)
            total_tps = sum(pr.eval_tps for pr in ok)
            print(f"\n  Avg throughput per model:  {avg_tps:.1f} tok/s")
            print(f"  Combined cluster output:   {total_tps:.1f} tok/s")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Ollama benchmark starting...")
    serial  = run_serial_benchmarks()
    parallel = run_parallel_test()
    print_report(serial, parallel)

if __name__ == "__main__":
    main()
