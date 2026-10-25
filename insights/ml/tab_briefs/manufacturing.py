"""Tab briefs for the Manufacturing dashboard (Rule 7: server-built sentences).

While no Work Order exists the OEE, Capacity, Forecast and Recommendations tabs
collapse into one "Production" tab. Every sentence names the missing
prerequisite using the payload's own notes.
"""

from . import action, brief, detail, plural


def _sentence(note) -> str:
    note = (note or "").strip()
    return note if not note or note.endswith(".") else note + "."


def _production(p: dict):
    pm = p.get("production_metrics") or {}
    if pm.get("total_work_orders") != 0:
        return None  # Work Orders exist: the four tabs keep their own bodies.
    notes = [
        (p.get("oee_analysis") or {}).get("message"),
        (p.get("capacity_utilization") or {}).get("message"),
        (p.get("quality_metrics") or {}).get("quality_data_note"),
    ]
    text = f"OEE is unmeasurable: {plural(0, 'Work Order')} recorded."
    text += "".join(f" {_sentence(n)}" for n in notes if n)
    mrs = pm.get("pending_material_requests")
    if mrs:
        text += f" {plural(mrs, 'material request')} pending."
    details = [
        detail(label, _sentence(note))
        for label, note in (
            ("OEE", (p.get("oee_analysis") or {}).get("message")),
            ("Capacity", (p.get("capacity_utilization") or {}).get("message")),
            ("Quality", (p.get("quality_metrics") or {}).get("quality_data_note")),
            ("Efficiency", ((p.get("efficiency_metrics") or {}).get("efficiency_data_note") or "").split(";")[0]),
            ("Costing", (p.get("cost_analysis") or {}).get("cost_data_note")),
            ("Forecast", (p.get("production_forecast") or {}).get("message")),
        )
        if note
    ]
    actions = [action("Record Work Orders", "OEE, capacity, cost and forecast figures all start from Work Orders; none exist for this period.")]
    if mrs:
        actions.append(action("Clear pending material requests", f"{plural(mrs, 'material request')} pending."))
    return brief("medium", text.strip(), details, actions)


def briefs(p: dict) -> dict:
    out = {"production": _production(p)}
    return {k: v for k, v in out.items() if v}
