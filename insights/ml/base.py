from __future__ import annotations
import frappe
import importlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    import pandas as pd


# Kept importable from here: every ML module already reaches for
# `insights.ml.base.sanitize_for_json`. The implementation moved to
# `insights.api.serialization` so `insights.api.response` can use it without
# dragging pandas and numpy into every web worker.
from insights.api.serialization import sanitize_for_json


class BaseMLModel(ABC):
    """Base class for all ML models"""
    
    def __init__(self):
        self.model_name = self.__class__.__name__
        self.last_trained = None
        self.model_version = "1.0"
        
    @abstractmethod
    def train(self) -> Dict[str, Any]:
        """Train the model"""
        pass
    
    @abstractmethod
    def predict(self, data: Any) -> Dict[str, Any]:
        """Make predictions"""
        pass
    
    def get_training_data(self, query: str, params=None) -> pd.DataFrame:
        """Execute SQL and return as DataFrame.

        `params` binds values the Frappe way. Without it callers reach for
        f-strings or `%`-formatting to get a value into the query, which is the
        `frappe-sql-format-injection` shape the standards forbid.
        """
        import pandas as pd

        result = (
            frappe.db.sql(query, params, as_dict=True)
            if params is not None
            else frappe.db.sql(query, as_dict=True)
        )
        # Convert frappe._dict objects to regular dicts for pandas compatibility
        if result:
            result = [dict(row) for row in result]
        return pd.DataFrame(result)
    
    def log_training(self, metrics: Dict[str, Any]):
        """Log training run - logs to frappe error log if ML Training Log doctype doesn't exist"""
        try:
            # Check if ML Training Log doctype exists
            if frappe.db.exists("DocType", "ML Training Log"):
                frappe.get_doc({
                    "doctype": "ML Training Log",
                    "model_name": self.model_name,
                    "model_version": self.model_version,
                    "training_date": frappe.utils.now(),
                    "metrics": json.dumps(metrics),
                    "status": "Completed"
                }).insert(ignore_permissions=True)
                frappe.db.commit()
            else:
                # Log to system log instead
                frappe.logger().info(f"ML Training: {self.model_name} v{self.model_version} - {json.dumps(metrics)}")
        except Exception as e:
            # Don't fail training if logging fails
            frappe.logger().warning(f"Failed to log ML training: {str(e)}")
    
    def _snapshot_path(self, cache_key: str) -> str:
        """Durable on-disk location for the last good payload of `cache_key`."""
        directory = frappe.get_site_path("private", "files", "insights_ml_snapshots")
        os.makedirs(directory, exist_ok=True)
        safe_name = re.sub(r"\W+", "_", cache_key)
        return os.path.join(directory, safe_name + ".json")

    def get_cached_results(self, cache_key: str, max_age_hours: int = 24) -> Optional[Dict]:
        """Get cached results if still valid"""
        cached = frappe.cache.get_value(cache_key)
        if cached:
            cached_time = cached.get("cached_at")
            if cached_time:
                age = datetime.now() - datetime.fromisoformat(cached_time)
                if age.total_seconds() < max_age_hours * 3600:
                    return cached.get("data")
        return None

    def get_last_good_results(self, cache_key: str) -> Optional[Dict]:
        """The last payload that computed successfully, however old.

        Redis holds the fresh copy, but it is wiped by `bench clear-cache`, by
        `bench migrate`, and by any Redis restart, and it expires regardless.
        Without this, every one of those events downgrades a dashboard to a
        "warming" placeholder until the next scheduler tick, even though the
        last computed numbers are still on disk and still useful.

        Stale numbers with a visible `stale_since` beat no dashboard at all.
        """
        try:
            path = self._snapshot_path(cache_key)
            if not os.path.exists(path):
                return None
            # `path` never contains caller input: `_snapshot_path` roots it at
            # `frappe.get_site_path` and reduces the key with
            # `re.sub(r"\W+", "_", ...)`, so no separator or traversal sequence
            # can survive into the filename.
            # nosemgrep: frappe-security-file-traversal
            with open(path, encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception as e:
            frappe.logger().warning(f"Could not read ML snapshot for {cache_key}: {e}")
            return None

        data = snapshot.get("data")
        if isinstance(data, dict) and snapshot.get("cached_at"):
            data = dict(data)
            data["stale_since"] = snapshot["cached_at"]
        return data

    def cache_results(self, cache_key: str, data: Dict, expires_in_hours: int = 24):
        """Cache results (sanitizes numpy/pandas scalars before storing)"""
        payload = {
            "data": sanitize_for_json(data),
            "cached_at": datetime.now().isoformat(),
        }
        frappe.cache.set_value(cache_key, payload, expires_in_sec=expires_in_hours * 3600)
        self._write_snapshot(cache_key, payload)

    def _write_snapshot(self, cache_key: str, payload: Dict):
        """Persist the last good payload, atomically.

        Written via a temp file in the same directory then renamed, so a reader
        never sees a half-written file and a crash mid-write cannot destroy the
        previous good copy. Never raises: losing the snapshot must not fail a
        training run that otherwise succeeded.
        """
        try:
            path = self._snapshot_path(cache_key)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, default=str)
                os.replace(tmp, path)
            except Exception:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as e:
            frappe.logger().warning(f"Could not write ML snapshot for {cache_key}: {e}")


def ensure_dependencies() -> Dict[str, Optional[str]]:
    """Which ML libraries this interpreter can import, and at what version.

    Previously returned bare booleans for a list that had drifted from reality:
    it probed `xgboost`, which the app no longer installs, and never mentioned
    `statsmodels`, which is what the sales forecast actually fits on. It also
    had no callers -- the only way to see its answer was to run it by hand over
    a bench shell, which is why "check the dependencies on production" kept
    living on a task list instead of being knowable.

    Now it reports versions rather than True/False, because "installed" was
    never the interesting question -- two benches disagreeing about which
    version is installed is what silently changes a model's behaviour. The
    `model_health` endpoint reads this, so the answer shows on the Machine
    Learning page for whatever site you are looking at.

    Returns a mapping of import name to version string, or None when the
    library cannot be imported.
    """
    found: Dict[str, Optional[str]] = {}
    for label, module_name in (
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("scikit-learn", "sklearn"),
        ("statsmodels", "statsmodels"),
        ("prophet", "prophet"),
    ):
        try:
            module = importlib.import_module(module_name)
            found[label] = getattr(module, "__version__", "unknown")
        except Exception:
            # ImportError for a missing package, but a broken native build
            # raises other things -- and for this report they mean the same.
            found[label] = None
    return found


def get_date_range(months_back: int = 12) -> Tuple[str, str]:
    """Get date range for queries"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months_back * 30)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
