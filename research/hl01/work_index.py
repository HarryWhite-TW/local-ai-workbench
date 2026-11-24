"""Host-owned index over the lab fixture. Model inputs never select a principal."""
import hashlib
import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "works.json"


class WorkIndex:
    def __init__(self, account="demo", workspace="studio"):
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.rows = {
            r["work_id"]: r for r in rows
            if r["account"] == account and r["workspace"] == workspace
        }

    def metadata(self, work_id):
        row = self.rows.get(work_id)
        if row is None:
            return {"decision": "unavailable"}
        digest = hashlib.sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return {**{k: row[k] for k in ("workspace", "work_id", "name", "date", "receipt", "status")},
                "source": f"works.json#{work_id}", "sha256": digest}

    def search(self, query=""):
        term = query.strip().casefold()
        return [self.metadata(row["work_id"]) for row in
                sorted(self.rows.values(), key=lambda r: (r["date"], r["work_id"]), reverse=True)
                if any(term in row[k].casefold() for k in ("name", "work_id", "receipt", "status", "date"))][:10]

    def detail(self, work_id, receipt, grants):
        row = self.rows.get(work_id)
        if row is None or row["receipt"] != receipt or (work_id, receipt) not in grants:
            return {"decision": "denied"}
        grants.remove((work_id, receipt))
        return {**self.metadata(work_id), "decision": "allowed", "evidence_text": row["detail"]}
