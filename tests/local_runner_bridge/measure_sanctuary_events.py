"""Measure real EventStore scan and Panel snapshot; creates only temporary fixtures."""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from test_sanctuary_stabilization import base, record, running_state, write_events


def main():
    rows = []
    for count in (1000, 2049, 10000, 50000, 100000):
        with tempfile.TemporaryDirectory(prefix="sanctuary-perf-") as directory:
            root = Path(directory).resolve()
            running_state(root)
            foreign = record(request="foreign-request-001", run="foreign-run-001")
            events = [foreign]*(count//2)+[record("execution.started"), record()]+[foreign]*(count-count//2-2)
            store = write_events(root / "events.jsonl", events)
            samples = {"read_ms": [], "snapshot_ms": []}
            for _ in range(5):
                start = time.perf_counter()
                window = store.read_current(base.REQUEST_ID)
                samples["read_ms"].append((time.perf_counter()-start)*1000)
                start = time.perf_counter()
                snapshot = base.build_workflow_snapshot(root, store, now=base.NOW)
                samples["snapshot_ms"].append((time.perf_counter()-start)*1000)
                assert window["run_id"] == snapshot["observability"]["run_id"] == base.RUN_ID
                assert snapshot["observability"]["request_event_count"] == 2
            rows.append({"event_count": count, "bytes": store.path.stat().st_size,
                         **{key: {"median": round(statistics.median(values), 2), "max": round(max(values), 2)}
                            for key, values in samples.items()}})
    result = {"complexity": "whole-file O(N) scan; bounded event retention; no database/index",
              "repetitions": 5, "measurements": rows}
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
