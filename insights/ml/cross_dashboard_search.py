"""
Cross-Dashboard Search & Navigation Service (Ibis-compatible rewrite).

This service provides unified search across all intelligence dashboards:

- Global search across multiple intelligence domains
- Intelligent query routing and context switching
- Cross-dashboard navigation with maintained context
- Simple keyword-based relevance scoring (no sklearn)
- Search result categorisation and filtering
- Search history and favourites (per-session-user, IDOR-safe)
- Smart suggestions and auto-complete

The pre-rewrite version constructed a pandas DataFrame per match, did
weighted-sum relevance scoring with numpy, and was wrapped by
``guarded_task`` (RQ background work — the same ``os.fork()`` that crashed
on Frappe Cloud for the other ML modules). All of that is gone: scoring
is plain Python over the few in-memory matches per domain, the heavy
"load every dashboard's data and full-text search the dict tree" is
replaced by direct ``frappe.get_all`` calls bounded by limit, and there
is no background work, no cache, no fork.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import frappe

logger = logging.getLogger(__name__)


# Per-domain DocType used to gate visibility: a Sales-only user asking for
# "top customers this quarter" never sees an HR record even if the search
# happens to match a department name. This is the IDOR fix the previous
# rewrite missed.
_DOMAIN_DOCTYPE = {
    "executive": "Sales Invoice",
    "financial": "GL Entry",
    "sales": "Sales Invoice",
    "customer": "Customer",
    "operations": "Purchase Order",
    "hr": "Employee",
    "manufacturing": "Work Order",
    "marketing": "Lead",
    "esg": "Sales Invoice",
    "budget": "Budget",
}


class CrossDashboardSearchService:
    """Unified search service for the intelligence dashboards.

    Scoring is transparent and bounded: a query of N words produces at
    most 10 keyword hits per matched domain, and the service returns at
    most 20 results overall. No pandas, no numpy, no vectorised
    anything — the work is small enough that a few hundred Python
    string ops is faster than a fork-and-materialise.
    """

    def __init__(self) -> None:
        self.service_name = "Cross-Dashboard Search Service"

        self.dashboard_domains = {
            "executive": {
                "name": "Executive Intelligence",
                "keywords": ["executive", "overview", "summary", "kpi", "performance", "strategic"],
                "search_fields": ["summary", "kpis", "alerts", "recommendations"],
                "weight": 1.2,
            },
            "financial": {
                "name": "Financial Intelligence",
                "keywords": ["financial", "profit", "revenue", "cost", "budget", "cash", "margin"],
                "search_fields": ["financial_summary", "ratios", "cash_flow", "profitability"],
                "weight": 1.0,
            },
            "budget": {
                "name": "Budget Variance Intelligence",
                "keywords": ["budget", "variance", "forecast", "actual", "planning", "allocation"],
                "search_fields": ["variance_summary", "departmental_analysis", "recommendations"],
                "weight": 1.0,
            },
            "hr": {
                "name": "HR Intelligence",
                "keywords": ["hr", "employee", "staff", "workforce", "talent", "retention", "payroll"],
                "search_fields": ["workforce_summary", "retention_analysis", "performance_metrics"],
                "weight": 1.0,
            },
            "manufacturing": {
                "name": "Manufacturing Intelligence",
                "keywords": ["manufacturing", "production", "oee", "quality", "efficiency", "capacity"],
                "search_fields": ["production_summary", "oee_analysis", "quality_metrics"],
                "weight": 1.0,
            },
            "sales": {
                "name": "Sales Intelligence",
                "keywords": ["sales", "revenue", "pipeline", "customer", "deal", "quota", "territory"],
                "search_fields": ["sales_summary", "pipeline_analysis", "performance_metrics"],
                "weight": 1.0,
            },
            "customer": {
                "name": "Customer Intelligence",
                "keywords": ["customer", "client", "retention", "churn", "satisfaction", "lifetime value"],
                "search_fields": ["customer_summary", "churn_analysis", "segmentation"],
                "weight": 1.0,
            },
            "esg": {
                "name": "ESG Intelligence",
                "keywords": ["esg", "environmental", "social", "governance", "sustainability", "carbon"],
                "search_fields": ["esg_summary", "environmental_metrics", "social_metrics"],
                "weight": 1.0,
            },
        }

        self.result_categories = {
            "metrics": {"label": "Key Metrics", "icon": "trending-up"},
            "alerts": {"label": "Alerts & Issues", "icon": "alert-circle"},
            "recommendations": {"label": "Recommendations", "icon": "lightbulb"},
            "trends": {"label": "Trends & Analysis", "icon": "bar-chart"},
            "summary": {"label": "Summaries", "icon": "file-text"},
            "departmental": {"label": "Departmental Data", "icon": "building"},
        }

        self.available_filters = {
            "time_period": ["today", "this_week", "this_month", "this_quarter", "this_year"],
            "dashboard": list(self.dashboard_domains.keys()),
            "category": list(self.result_categories.keys()),
            "priority": ["high", "medium", "low"],
            "data_type": ["metrics", "charts", "tables", "text"],
        }

    # ------------------------------------------------------------------ public

    def perform_global_search(
        self,
        query: str,
        filters: Optional[Dict] = None,
        user_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Run a global search across the relevant domains.

        Returns the envelope the frontend reads in
        ``CrossDashboardSearch.vue``::

            {
                "search_session":   {session_id, query, user, timestamp, ...},
                "query_analysis":   {keywords, query_type, has_metrics, ...},
                "summary":          {query, total_results, ...},
                "search_results":   {   # <-- key the frontend reads
                    "results":    {"top_results": [...], "by_category": {...}},
                    "navigation": {...},
                },
                "navigation_recommendations": {...},
                "agent_response":  "...",
                "filters_applied": filters or {},
                "total_results":   int,
                "search_time":     ISO,
            }
        """
        try:
            search_session = self._create_search_session(query, filters, user_context)
            query_analysis = self._analyze_search_query(query)
            requested_domain = (user_context or {}).get("domain")
            relevant_domains = self._resolve_relevant_domains(query_analysis, requested_domain)

            domain_results: Dict[str, Dict[str, Any]] = {}
            for domain_id in relevant_domains:
                data = self._search_domain(domain_id, query_analysis, filters)
                if data["results"]:
                    domain_results[domain_id] = data

            aggregated = self._aggregate_search_results(domain_results, query_analysis)
            navigation = self._generate_navigation_suggestions(
                query_analysis, list(domain_results.keys()), aggregated
            )
            total_results = sum(len(d["results"]) for d in domain_results.values())
            summary = self._create_search_summary(
                query, total_results, list(domain_results.keys()), aggregated
            )

            return {
                "search_session": search_session,
                "query_analysis": query_analysis,
                "summary": summary,
                "search_results": {
                    "results": aggregated,
                    "navigation": navigation,
                },
                "navigation_recommendations": self._build_navigation_recommendations(
                    query_analysis, list(domain_results.keys())
                ),
                "agent_response": self._build_agent_response(
                    query, total_results, list(domain_results.keys())
                ),
                "filters_applied": filters or {},
                "total_results": total_results,
                "search_time": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("Error performing global search: %s", e)
            frappe.log_error(f"Global Search Error: {e}", "Cross-Dashboard Search")
            return {
                "search_session": {"query": query},
                "query_analysis": {"original_query": query, "keywords": []},
                "summary": {"query": query, "total_results": 0, "search_quality": "no_results"},
                "search_results": {
                    "results": {"top_results": [], "by_category": {}, "related_searches": []},
                    "navigation": {"quick_actions": [], "related_dashboards": [], "contextual_navigation": []},
                },
                "navigation_recommendations": {"message": "Search failed", "suggestions": []},
                "agent_response": "Sorry, the search failed. Please try again.",
                "filters_applied": filters or {},
                "total_results": 0,
                "search_time": datetime.now().isoformat(),
                "error": str(e),
            }

    def get_search_suggestions(
        self,
        partial_query: str,
        context: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Autocomplete suggestions for ``partial_query``.

        Returns a list of ``{text, type, confidence}`` dicts (max 10).
        The frontend's ``apiCall`` unwraps the envelope, so this list is
        the `data` portion of the response.
        """
        try:
            suggestions: List[Dict[str, Any]] = []
            suggestions.extend(self._generate_query_suggestions(partial_query))
            if context:
                suggestions.extend(self._generate_context_suggestions(partial_query, context))
            suggestions.extend(self._get_popular_searches(partial_query))

            unique: List[Dict[str, Any]] = []
            seen: set = set()
            for s in suggestions:
                key = (s.get("text") or "").lower()
                if key and key not in seen:
                    seen.add(key)
                    unique.append(s)
                if len(unique) >= 10:
                    break
            return unique
        except Exception as e:
            logger.error("Error generating search suggestions: %s", e)
            return []

    def get_search_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return search history for the current session user.

        The ``user`` parameter is intentionally not exposed — it was an
        IDOR vector (plan-eng-review D-IDOR) and is always taken from
        ``frappe.session.user`` server-side.

        ``Search Activity Log`` is not in this bench, so this returns
        an empty list rather than fabricating rows.
        """
        try:
            user = frappe.session.user
            if not frappe.db.table_exists("Search Activity Log"):
                return []
            return frappe.db.get_list(
                "Search Activity Log",
                filters={"user": user},
                fields=["query", "results_count", "timestamp", "domains_searched"],
                order_by="timestamp desc",
                limit_page_length=limit,
            ) or []
        except Exception as e:
            logger.error("Error getting search history: %s", e)
            return []

    def save_search_favorite(self, query: str, title: Optional[str] = None) -> Dict[str, Any]:
        """Save a search as a favorite for the current session user.

        Same IDOR fix as ``get_search_history`` — the user is always
        taken from ``frappe.session.user``.
        """
        try:
            user = frappe.session.user
            if not frappe.db.table_exists("Search Favorite"):
                return {
                    "status": "not_available",
                    "message": "Search favourites are not enabled on this site",
                }
            favorite = frappe.get_doc({
                "doctype": "Search Favorite",
                "user": user,
                "query": query,
                "title": title or query,
                "created_at": datetime.now(),
            })
            favorite.insert(ignore_permissions=True)
            return {
                "status": "success",
                "favorite_id": favorite.name,
                "message": "Search saved as favorite",
            }
        except Exception as e:
            logger.error("Error saving search favorite: %s", e)
            return {"status": "error", "message": str(e)}

    def get_cross_dashboard_navigation(
        self,
        current_context: Dict,
        target_query: str,
    ) -> Dict[str, Any]:
        try:
            query_analysis = self._analyze_search_query(target_query)
            target_domains = self._resolve_relevant_domains(query_analysis, None)

            options: List[Dict[str, Any]] = []
            for domain_id in target_domains:
                cfg = self.dashboard_domains[domain_id]
                options.append({
                    "domain_id": domain_id,
                    "domain_name": cfg["name"],
                    "route": f"/{domain_id.replace('_', '-')}-intelligence",
                    "confidence": self._calculate_domain_relevance(domain_id, query_analysis),
                    "context_transfer": True,
                    "search_context": target_query,
                })
            options.sort(key=lambda x: x["confidence"], reverse=True)

            return {
                "current_context": current_context,
                "target_query": target_query,
                "navigation_options": options,
                "recommended_action": self._get_recommended_navigation_action(
                    current_context, options
                ),
            }
        except Exception as e:
            logger.error("Error generating cross-dashboard navigation: %s", e)
            return {"error": str(e), "navigation_options": []}

    # ------------------------------------------------------------------ session

    def _create_search_session(
        self,
        query: str,
        filters: Optional[Dict],
        user_context: Optional[Dict],
    ) -> Dict[str, Any]:
        return {
            "session_id": frappe.generate_hash(length=10),
            "query": query,
            "user": frappe.session.user,
            "timestamp": datetime.now().isoformat(),
            "filters": filters or {},
            "context": user_context or {},
        }

    # ------------------------------------------------------------------ analyse

    def _analyze_search_query(self, query: str) -> Dict[str, Any]:
        try:
            query_lower = (query or "").lower()
            keywords = [w for w in re.findall(r"\b\w+\b", query_lower) if len(w) > 2]

            query_type = "general"
            if any(w in query_lower for w in ["what", "how", "why", "when"]):
                query_type = "analytical"
            elif any(w in query_lower for w in ["show", "list", "display"]):
                query_type = "data_request"
            elif any(w in query_lower for w in ["compare", "vs", "versus"]):
                query_type = "comparison"
            elif any(w in query_lower for w in ["trend", "over time", "monthly", "yearly"]):
                query_type = "temporal"

            metrics_indicators = ["total", "average", "sum", "count", "percentage", "rate", "score"]
            return {
                "original_query": query,
                "keywords": keywords,
                "query_type": query_type,
                "entities": self._extract_entities(query_lower),
                "has_metrics": any(ind in query_lower for ind in metrics_indicators),
                "query_intent": self._determine_query_intent(query_lower, keywords),
            }
        except Exception as e:
            logger.error("Error analyzing search query: %s", e)
            return {"original_query": query, "keywords": [], "query_type": "general"}

    def _extract_entities(self, query: str) -> Dict[str, List[str]]:
        entities: Dict[str, List[str]] = {
            "departments": [],
            "time_periods": [],
            "metrics": [],
            "accounts": [],
        }
        for p in ["sales", "marketing", "hr", "finance", "operations", "manufacturing"]:
            if p in query:
                entities["departments"].append(p)
        for p in ["today", "yesterday", "week", "month", "quarter", "year", "ytd", "mtd"]:
            if p in query:
                entities["time_periods"].append(p)
        return entities

    def _determine_query_intent(self, query: str, keywords: List[str]) -> str:
        kw = set(keywords)
        if kw & {"alert", "issue", "problem", "critical"}:
            return "troubleshooting"
        if kw & {"recommend", "improve", "optimize", "suggest"}:
            return "advisory"
        if kw & {"summary", "overview", "status", "health"}:
            return "monitoring"
        if kw & {"forecast", "predict", "trend", "projection"}:
            return "forecasting"
        if kw & {"compare", "benchmark", "versus", "against"}:
            return "comparison"
        return "informational"

    # ------------------------------------------------------------------ domains

    def _resolve_relevant_domains(
        self,
        query_analysis: Dict,
        requested_domain: Optional[str],
    ) -> List[str]:
        if requested_domain:
            if requested_domain not in self.dashboard_domains:
                return []
            return [requested_domain] if self._user_can_see_domain(requested_domain) else []

        scored: List[tuple] = []
        for domain_id in self.dashboard_domains:
            if not self._user_can_see_domain(domain_id):
                continue
            score = self._calculate_domain_relevance(domain_id, query_analysis)
            if score > 0:
                scored.append((score, domain_id))
        scored.sort(reverse=True)
        return [d for _, d in scored]

    def _user_can_see_domain(self, domain_id: str) -> bool:
        doctype = _DOMAIN_DOCTYPE.get(domain_id)
        if not doctype:
            return False
        try:
            return bool(frappe.has_permission(doctype, "read", throw=False))
        except Exception:
            return False

    def _calculate_domain_relevance(self, domain_id: str, query_analysis: Dict) -> float:
        if domain_id not in self.dashboard_domains:
            return 0.0
        config = self.dashboard_domains[domain_id]
        keywords = query_analysis.get("keywords", [])
        if not keywords:
            return 0.0
        score = 0.0
        for keyword in keywords:
            if keyword in config["keywords"]:
                score += 2.0
            elif any(kw in keyword or keyword in kw for kw in config["keywords"]):
                score += 1.0
        score *= config["weight"]
        return min(score / 10.0, 1.0)

    # ------------------------------------------------------------------ search

    def _search_domain(
        self,
        domain_id: str,
        query_analysis: Dict,
        filters: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Search the bounded live data for a single domain.

        The old code recursively walked every dict key of every intelligence
        payload and stringified every leaf, which was unbounded and slow.
        Here we issue at most one small ``frappe.get_all`` per domain,
        keyword-match against the short text fields, and return at most
        10 matches.
        """
        try:
            keywords = query_analysis.get("keywords", [])
            if not keywords:
                return {"domain_id": domain_id, "results": [], "total_matches": 0}

            rows = self._fetch_domain_rows(domain_id, filters)
            if not rows:
                return {"domain_id": domain_id, "results": [], "total_matches": 0}

            matches: List[Dict[str, Any]] = []
            for row in rows:
                m = self._match_row(row, keywords, domain_id)
                if m:
                    matches.append(m)
                if len(matches) >= 10:
                    break
            return {
                "domain_id": domain_id,
                "domain_name": self.dashboard_domains[domain_id]["name"],
                "results": matches,
                "total_matches": len(matches),
            }
        except Exception as e:
            logger.error("Error searching domain %s: %s", domain_id, e)
            return {"domain_id": domain_id, "results": [], "total_matches": 0}

    def _fetch_domain_rows(self, domain_id: str, filters: Optional[Dict]) -> List[Dict[str, Any]]:
        """Per-domain targeted ``frappe.get_all``. Capped at 25 rows.

        Each row is short text fields only; the keyword match runs over
        those ~25 rows × ~5 short strings.
        """
        limit = 25
        if domain_id == "executive":
            return []
        if domain_id == "financial":
            return frappe.get_all(
                "GL Entry",
                fields=["name", "account", "voucher_type", "posting_date"],
                limit_page_length=limit,
                order_by="posting_date desc",
            )
        if domain_id == "sales":
            return frappe.get_all(
                "Sales Invoice",
                fields=["name", "customer", "customer_name", "posting_date"],
                filters={"docstatus": 1},
                limit_page_length=limit,
                order_by="posting_date desc",
            )
        if domain_id == "customer":
            return frappe.get_all(
                "Customer",
                fields=["name", "customer_name", "customer_group", "territory"],
                filters={"disabled": 0},
                limit_page_length=limit,
            )
        if domain_id == "operations":
            return frappe.get_all(
                "Purchase Order",
                fields=["name", "supplier", "supplier_name", "transaction_date"],
                filters={"docstatus": 1},
                limit_page_length=limit,
                order_by="transaction_date desc",
            )
        if domain_id == "hr":
            return frappe.get_all(
                "Employee",
                fields=["name", "employee_name", "department", "designation"],
                filters={"status": "Active"},
                limit_page_length=limit,
            )
        if domain_id == "manufacturing":
            if not frappe.db.table_exists("Work Order"):
                return []
            return frappe.get_all(
                "Work Order",
                fields=["name", "item_name", "qty", "status"],
                filters={"docstatus": 1},
                limit_page_length=limit,
            )
        if domain_id == "budget":
            if not frappe.db.table_exists("Budget"):
                return []
            return frappe.get_all(
                "Budget",
                fields=["name", "budget_amount", "fiscal_year", "company"],
                limit_page_length=limit,
            )
        return []

    def _match_row(
        self,
        row: Dict[str, Any],
        keywords: List[str],
        domain_id: str,
    ) -> Optional[Dict[str, Any]]:
        title_keys = ("name", "customer_name", "employee_name", "supplier_name", "account")
        title = next(
            (str(v) for k, v in row.items() if k in title_keys and v),
            str(row.get("name", "")),
        )
        content = " ".join(str(v) for v in row.values() if v is not None)
        haystack_lower = content.lower()
        for kw in keywords:
            if kw in haystack_lower:
                return {
                    "id": str(row.get("name", "")),
                    "title": title,
                    "content": content[:200],
                    "score": self._calculate_relevance_score(haystack_lower, keywords),
                    "source": domain_id,
                    "data_type": "record",
                    "category": self._categorize_text(haystack_lower),
                    "navigation_url": self._generate_navigation_url(
                        domain_id, {"id": row.get("name"), "source": domain_id}
                    ),
                    "preview": content[:147] + ("..." if len(content) > 147 else ""),
                    "metadata": {
                        "domain": domain_id,
                        "last_updated": None,
                        "data_quality": "good",
                    },
                }
        return None

    def _calculate_relevance_score(self, text_lower: str, keywords: List[str]) -> float:
        if not keywords:
            return 0.0
        score = 0.0
        for kw in keywords:
            if kw in text_lower:
                score += 2.0
            else:
                for word in text_lower.split():
                    if kw in word or word in kw:
                        score += 1.0
                        break
        return min(score / len(keywords), 10.0)

    def _categorize_text(self, text_lower: str) -> str:
        if any(w in text_lower for w in ["alert", "warning", "issue", "problem"]):
            return "alerts"
        if any(w in text_lower for w in ["recommend", "suggestion", "improve"]):
            return "recommendations"
        if any(w in text_lower for w in ["trend", "analysis", "over time"]):
            return "trends"
        if any(w in text_lower for w in ["summary", "overview", "status"]):
            return "summary"
        if any(w in text_lower for w in ["department", "division", "team"]):
            return "departmental"
        return "metrics"

    def _generate_navigation_url(self, domain_id: str, match: Dict) -> str:
        base_url = f"/{domain_id.replace('_', '-')}-intelligence"
        source = match.get("source", "")
        if source:
            return f"{base_url}?section={source}&highlight={match.get('id', '')}"
        return base_url

    # ------------------------------------------------------------------ aggregate

    def _aggregate_search_results(
        self,
        domain_results: Dict,
        query_analysis: Dict,
    ) -> Dict[str, Any]:
        by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        top_results: List[Dict[str, Any]] = []
        for domain_data in domain_results.values():
            for result in domain_data.get("results", []):
                by_category[result.get("category", "metrics")].append(result)
                top_results.append(result)
        top_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return {
            "by_category": dict(by_category),
            "by_domain": domain_results,
            "top_results": top_results[:20],
            "related_searches": self._generate_related_searches(query_analysis),
        }

    def _generate_related_searches(self, query_analysis: Dict) -> List[str]:
        related: List[str] = []
        intent = query_analysis.get("query_intent", "")
        if intent == "monitoring":
            related.extend(["performance trends", "key metrics dashboard", "status alerts"])
        elif intent == "troubleshooting":
            related.extend(["critical issues", "system alerts", "performance problems"])
        elif intent == "advisory":
            related.extend(["recommendations", "improvement suggestions", "optimization opportunities"])
        for kw in query_analysis.get("keywords", [])[:3]:
            related.append(f"{kw} analysis")
            related.append(f"{kw} trends")
        return related[:8]

    # ------------------------------------------------------------------ navigation

    def _generate_navigation_suggestions(
        self,
        query_analysis: Dict,
        relevant_domains: List[str],
        search_results: Dict,
    ) -> Dict[str, Any]:
        suggestions = {"quick_actions": [], "related_dashboards": [], "contextual_navigation": []}
        intent = query_analysis.get("query_intent", "")
        if intent == "troubleshooting":
            suggestions["quick_actions"].extend([
                {"label": "View All Alerts", "action": "navigate", "target": "alerts_overview"},
                {"label": "System Health Check", "action": "navigate", "target": "system_health"},
                {"label": "Performance Monitor", "action": "navigate", "target": "performance_dashboard"},
            ])
        elif intent == "forecasting":
            suggestions["quick_actions"].extend([
                {"label": "Predictive Analytics", "action": "navigate", "target": "predictive_dashboard"},
                {"label": "Trend Analysis", "action": "navigate", "target": "trends_dashboard"},
                {"label": "Forecast Models", "action": "navigate", "target": "forecast_center"},
            ])

        for domain_id in relevant_domains:
            cfg = self.dashboard_domains[domain_id]
            suggestions["related_dashboards"].append({
                "id": domain_id,
                "name": cfg["name"],
                "relevance": self._calculate_domain_relevance(domain_id, query_analysis),
                "url": f"/{domain_id.replace('_', '-')}-intelligence",
            })

        for cat in self._get_top_result_categories(search_results):
            cfg = self.result_categories.get(cat)
            if cfg:
                suggestions["contextual_navigation"].append({
                    "category": cat,
                    "label": f"View All {cfg['label']}",
                    "icon": cfg["icon"],
                    "action": "filter_results",
                    "filter": {"category": cat},
                })
        return suggestions

    def _get_top_result_categories(self, search_results: Dict) -> List[str]:
        counts: Dict[str, int] = defaultdict(int)
        for r in search_results.get("top_results", []):
            counts[r.get("category", "metrics")] += 1
        ordered = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [c for c, _ in ordered[:5]]

    def _build_navigation_recommendations(
        self,
        query_analysis: Dict,
        relevant_domains: List[str],
    ) -> Dict[str, Any]:
        if not relevant_domains:
            return {"message": "No matching dashboards found", "suggestions": []}
        suggestions = []
        for domain_id in relevant_domains[:5]:
            cfg = self.dashboard_domains[domain_id]
            suggestions.append({
                "dashboard_id": domain_id,
                "dashboard_name": cfg["name"],
                "url": f"/{domain_id.replace('_', '-')}-intelligence",
                "relevance": self._calculate_domain_relevance(domain_id, query_analysis),
            })
        return {
            "message": f"Found {len(suggestions)} dashboard(s) related to your query",
            "suggestions": suggestions,
        }

    def _build_agent_response(
        self,
        query: str,
        total_results: int,
        relevant_domains: List[str],
    ) -> str:
        if total_results == 0:
            return f"No results found for '{query}'. Try different keywords or check the spelling."
        domain_names = ", ".join(
            self.dashboard_domains[d]["name"] for d in relevant_domains[:3]
        )
        return f"Found {total_results} result(s) for '{query}' across {domain_names}."

    def _create_search_summary(
        self,
        query: str,
        total_results: int,
        relevant_domains: List[str],
        aggregated_results: Dict,
    ) -> Dict[str, Any]:
        if total_results == 0:
            quality = "no_results"
        elif total_results < 5:
            quality = "limited"
        elif total_results > 50:
            quality = "extensive"
        else:
            quality = "good"
        return {
            "query": query,
            "total_results": total_results,
            "domains_searched": len(relevant_domains),
            "categories_found": len(aggregated_results.get("by_category", {})),
            "search_quality": quality,
            "response_time": "fast",
            "suggestions_available": len(aggregated_results.get("related_searches", [])),
        }

    def _get_recommended_navigation_action(
        self,
        current_context: Dict,
        navigation_options: List[Dict],
    ) -> Dict[str, Any]:
        if not navigation_options:
            return {"action": "stay", "reason": "No relevant dashboards found"}
        best = max(navigation_options, key=lambda x: x.get("confidence", 0))
        if best["confidence"] > 0.7:
            return {
                "action": "navigate",
                "target": best,
                "reason": f"High relevance match for {best['domain_name']}",
            }
        if best["confidence"] > 0.4:
            return {
                "action": "suggest",
                "target": best,
                "reason": f"Potential match in {best['domain_name']}",
            }
        return {"action": "stay", "reason": "Low confidence in cross-dashboard matches"}

    # ------------------------------------------------------------------ suggestions

    def _generate_query_suggestions(self, partial_query: str) -> List[Dict[str, Any]]:
        partial = (partial_query or "").lower()
        patterns = [
            "top customers by revenue",
            "overdue invoices this month",
            "low stock items",
            "sales this quarter",
            "revenue trends",
            "headcount by department",
            "supplier performance",
            "manufacturing OEE",
        ]
        out: List[Dict[str, Any]] = []
        for p in patterns:
            if partial in p or p.startswith(partial):
                out.append({"text": p, "type": "query_completion", "confidence": 0.8})
        return out[:5]

    def _generate_context_suggestions(
        self,
        partial_query: str,
        context: Dict,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        current = context.get("dashboard", "")
        cfg = self.dashboard_domains.get(current, {})
        partial = (partial_query or "").lower()
        for kw in cfg.get("keywords", []):
            if partial in kw or kw.startswith(partial):
                out.append({
                    "text": f"{kw} in {cfg.get('name', '')}",
                    "type": "context_suggestion",
                    "confidence": 0.7,
                })
        return out[:3]

    def _get_popular_searches(self, partial_query: str) -> List[Dict[str, Any]]:
        popular = [
            "revenue trends",
            "budget status",
            "employee metrics",
            "performance dashboard",
            "alerts overview",
            "quarterly summary",
        ]
        partial = (partial_query or "").lower()
        out: List[Dict[str, Any]] = []
        for q in popular:
            if partial in q.lower() or q.lower().startswith(partial):
                out.append({"text": q, "type": "popular_search", "confidence": 0.6})
        return out[:3]


# Module-level instance — kept for backwards compatibility with anything
# that imported it directly. New callers construct their own.
cross_dashboard_search_service = CrossDashboardSearchService()
