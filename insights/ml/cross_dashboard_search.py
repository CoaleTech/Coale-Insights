"""
Cross-Dashboard Search & Navigation Service

This service provides unified search capabilities across all intelligence dashboards including:
- Global search across multiple intelligence domains
- Intelligent query routing and context switching  
- Cross-dashboard navigation with maintained context
- Semantic search with relevance scoring
- Search result categorization and filtering
- Search history and favorites management
- Smart suggestions and auto-complete functionality

Author: AI Assistant
Version: 1.0.0
"""

import frappe
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional, Tuple
import re
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class CrossDashboardSearchService:
    """
    Unified search service for all intelligence dashboards
    
    Features:
    - Multi-domain search across all intelligence modules
    - Semantic search with context awareness
    - Intelligent result ranking and categorization
    - Cross-dashboard navigation support
    - Search history and analytics
    """
    
    def __init__(self):
        """Initialize Cross-Dashboard Search Service"""
        self.service_name = "Cross-Dashboard Search Service"
        
        # Define searchable dashboard domains
        self.dashboard_domains = {
            "executive": {
                "name": "Executive Intelligence",
                "keywords": ["executive", "overview", "summary", "kpi", "performance", "strategic"],
                "search_fields": ["summary", "kpis", "alerts", "recommendations"],
                "weight": 1.2  # Higher weight for executive content
            },
            "financial": {
                "name": "Financial Intelligence", 
                "keywords": ["financial", "profit", "revenue", "cost", "budget", "cash", "margin"],
                "search_fields": ["financial_summary", "ratios", "cash_flow", "profitability"],
                "weight": 1.0
            },
            "budget": {
                "name": "Budget Variance Intelligence",
                "keywords": ["budget", "variance", "forecast", "actual", "planning", "allocation"],
                "search_fields": ["variance_summary", "departmental_analysis", "recommendations"],
                "weight": 1.0
            },
            "hr": {
                "name": "HR Intelligence",
                "keywords": ["hr", "employee", "staff", "workforce", "talent", "retention", "payroll"],
                "search_fields": ["workforce_summary", "retention_analysis", "performance_metrics"],
                "weight": 1.0
            },
            "manufacturing": {
                "name": "Manufacturing Intelligence",
                "keywords": ["manufacturing", "production", "oee", "quality", "efficiency", "capacity"],
                "search_fields": ["production_summary", "oee_analysis", "quality_metrics"],
                "weight": 1.0
            },
            "sales": {
                "name": "Sales Intelligence",
                "keywords": ["sales", "revenue", "pipeline", "customer", "deal", "quota", "territory"],
                "search_fields": ["sales_summary", "pipeline_analysis", "performance_metrics"],
                "weight": 1.0
            },
            "customer": {
                "name": "Customer Intelligence",
                "keywords": ["customer", "client", "retention", "churn", "satisfaction", "lifetime value"],
                "search_fields": ["customer_summary", "churn_analysis", "segmentation"],
                "weight": 1.0
            },
            "esg": {
                "name": "ESG Intelligence",
                "keywords": ["esg", "environmental", "social", "governance", "sustainability", "carbon"],
                "search_fields": ["esg_summary", "environmental_metrics", "social_metrics"],
                "weight": 1.0
            }
        }
        
        # Search result categories
        self.result_categories = {
            "metrics": {"label": "Key Metrics", "icon": "trending-up"},
            "alerts": {"label": "Alerts & Issues", "icon": "alert-circle"},
            "recommendations": {"label": "Recommendations", "icon": "lightbulb"},
            "trends": {"label": "Trends & Analysis", "icon": "bar-chart"},
            "summary": {"label": "Summaries", "icon": "file-text"},
            "departmental": {"label": "Departmental Data", "icon": "building"}
        }
        
        # Search filters
        self.available_filters = {
            "time_period": ["today", "this_week", "this_month", "this_quarter", "this_year"],
            "dashboard": list(self.dashboard_domains.keys()),
            "category": list(self.result_categories.keys()),
            "priority": ["high", "medium", "low"],
            "data_type": ["metrics", "charts", "tables", "text"]
        }
    
    def perform_global_search(self, query: str, filters: Dict = None, 
                             user_context: Dict = None) -> Dict[str, Any]:
        """
        Perform comprehensive search across all intelligence dashboards
        
        Args:
            query: Search query string
            filters: Optional filters for search results
            user_context: User context for personalization
            
        Returns:
            Comprehensive search results with categorization and navigation
        """
        try:
            logger.info(f"Performing global search for: {query}")
            
            # Initialize search session
            search_session = self._create_search_session(query, filters, user_context)
            
            # Analyze query intent and extract keywords
            query_analysis = self._analyze_search_query(query)
            
            # Determine relevant dashboard domains
            relevant_domains = self._identify_relevant_domains(query_analysis)
            
            # Search each relevant domain
            domain_results = {}
            total_results = 0
            
            for domain_id in relevant_domains:
                domain_data = self._search_domain(domain_id, query_analysis, filters)
                if domain_data["results"]:
                    domain_results[domain_id] = domain_data
                    total_results += len(domain_data["results"])
            
            # Aggregate and rank results
            aggregated_results = self._aggregate_search_results(domain_results, query_analysis)
            
            # Generate navigation suggestions
            navigation_suggestions = self._generate_navigation_suggestions(
                query_analysis, relevant_domains, aggregated_results
            )
            
            # Create search summary
            search_summary = self._create_search_summary(
                query, total_results, relevant_domains, aggregated_results
            )
            
            # Log search for analytics
            self._log_search_activity(search_session, aggregated_results)
            
            return {
                "search_session": search_session,
                "query_analysis": query_analysis,
                "summary": search_summary,
                "results": aggregated_results,
                "navigation": navigation_suggestions,
                "filters_applied": filters or {},
                "total_results": total_results,
                "search_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error performing global search: {e}")
            frappe.log_error(f"Global Search Error: {str(e)}", "Cross-Dashboard Search")
            return {"error": str(e), "results": [], "total_results": 0}
    
    def get_search_suggestions(self, partial_query: str, context: Dict = None) -> List[Dict[str, Any]]:
        """Generate intelligent search suggestions and auto-complete"""
        try:
            suggestions = []
            
            # Query-based suggestions
            query_suggestions = self._generate_query_suggestions(partial_query)
            suggestions.extend(query_suggestions)
            
            # Context-based suggestions
            if context:
                context_suggestions = self._generate_context_suggestions(partial_query, context)
                suggestions.extend(context_suggestions)
            
            # Popular searches
            popular_suggestions = self._get_popular_searches(partial_query)
            suggestions.extend(popular_suggestions)
            
            # Remove duplicates and limit results
            unique_suggestions = []
            seen = set()
            for suggestion in suggestions:
                key = suggestion.get("text", "").lower()
                if key not in seen and len(unique_suggestions) < 10:
                    seen.add(key)
                    unique_suggestions.append(suggestion)
            
            return unique_suggestions
            
        except Exception as e:
            logger.error(f"Error generating search suggestions: {e}")
            return []
    
    def get_search_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get search history for the current session user (never caller-supplied)."""
        try:
            user = frappe.session.user
            
            search_history = frappe.db.get_list(
                "Search Activity Log",
                filters={"user": user},
                fields=["query", "results_count", "timestamp", "domains_searched"],
                order_by="timestamp desc",
                limit=limit
            )
            
            return search_history
            
        except Exception as e:
            logger.error(f"Error getting search history: {e}")
            return []
    
    def save_search_favorite(self, query: str, title: str = None) -> Dict[str, Any]:
        """Save search as favorite for the current session user (never caller-supplied)."""
        try:
            user = frappe.session.user
            
            favorite = frappe.get_doc({
                "doctype": "Search Favorite",
                "user": user,
                "query": query,
                "title": title or query,
                "created_at": datetime.now()
            })
            favorite.insert(ignore_permissions=True)
            
            return {
                "status": "success",
                "favorite_id": favorite.name,
                "message": "Search saved as favorite"
            }
            
        except Exception as e:
            logger.error(f"Error saving search favorite: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_cross_dashboard_navigation(self, current_context: Dict, 
                                       target_query: str) -> Dict[str, Any]:
        """Generate cross-dashboard navigation suggestions"""
        try:
            # Analyze target query
            query_analysis = self._analyze_search_query(target_query)
            
            # Determine best dashboard for the query
            target_domains = self._identify_relevant_domains(query_analysis)
            
            # Generate navigation options
            navigation_options = []
            
            for domain_id in target_domains:
                domain = self.dashboard_domains[domain_id]
                
                option = {
                    "domain_id": domain_id,
                    "domain_name": domain["name"],
                    "route": f"/{domain_id.replace('_', '-')}-intelligence",
                    "confidence": self._calculate_domain_relevance(domain_id, query_analysis),
                    "context_transfer": True,
                    "search_context": target_query
                }
                navigation_options.append(option)
            
            # Sort by relevance
            navigation_options.sort(key=lambda x: x["confidence"], reverse=True)
            
            return {
                "current_context": current_context,
                "target_query": target_query,
                "navigation_options": navigation_options,
                "recommended_action": self._get_recommended_navigation_action(
                    current_context, navigation_options
                )
            }
            
        except Exception as e:
            logger.error(f"Error generating cross-dashboard navigation: {e}")
            return {"error": str(e), "navigation_options": []}
    
    # Private helper methods
    
    def _create_search_session(self, query: str, filters: Dict, user_context: Dict) -> Dict[str, Any]:
        """Create unique search session"""
        return {
            "session_id": frappe.generate_hash(length=10),
            "query": query,
            "user": frappe.session.user,
            "timestamp": datetime.now().isoformat(),
            "filters": filters or {},
            "context": user_context or {}
        }
    
    def _analyze_search_query(self, query: str) -> Dict[str, Any]:
        """Analyze search query to extract intent and keywords"""
        try:
            query_lower = query.lower()
            
            # Extract keywords
            keywords = re.findall(r'\b\w+\b', query_lower)
            keywords = [k for k in keywords if len(k) > 2]  # Filter short words
            
            # Identify query type
            query_type = "general"
            if any(word in query_lower for word in ["what", "how", "why", "when"]):
                query_type = "analytical"
            elif any(word in query_lower for word in ["show", "list", "display"]):
                query_type = "data_request"
            elif any(word in query_lower for word in ["compare", "vs", "versus"]):
                query_type = "comparison"
            elif any(word in query_lower for word in ["trend", "over time", "monthly", "yearly"]):
                query_type = "temporal"
            
            # Extract entities (simplified)
            entities = self._extract_entities(query_lower)
            
            # Detect metrics requests
            metrics_indicators = ["total", "average", "sum", "count", "percentage", "rate", "score"]
            has_metrics = any(indicator in query_lower for indicator in metrics_indicators)
            
            return {
                "original_query": query,
                "keywords": keywords,
                "query_type": query_type,
                "entities": entities,
                "has_metrics": has_metrics,
                "query_intent": self._determine_query_intent(query_lower, keywords)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing search query: {e}")
            return {"original_query": query, "keywords": [], "query_type": "general"}
    
    def _extract_entities(self, query: str) -> Dict[str, List[str]]:
        """Extract entities from query (simplified NER)"""
        entities = {
            "departments": [],
            "time_periods": [],
            "metrics": [],
            "accounts": []
        }
        
        # Department patterns
        dept_patterns = ["sales", "marketing", "hr", "finance", "operations", "manufacturing"]
        for pattern in dept_patterns:
            if pattern in query:
                entities["departments"].append(pattern)
        
        # Time period patterns
        time_patterns = ["today", "yesterday", "week", "month", "quarter", "year", "ytd", "mtd"]
        for pattern in time_patterns:
            if pattern in query:
                entities["time_periods"].append(pattern)
        
        return entities
    
    def _determine_query_intent(self, query: str, keywords: List[str]) -> str:
        """Determine the primary intent of the search query"""
        # Intent classification based on keywords
        if any(word in keywords for word in ["alert", "issue", "problem", "critical"]):
            return "troubleshooting"
        elif any(word in keywords for word in ["recommend", "improve", "optimize", "suggest"]):
            return "advisory"
        elif any(word in keywords for word in ["summary", "overview", "status", "health"]):
            return "monitoring"
        elif any(word in keywords for word in ["forecast", "predict", "trend", "projection"]):
            return "forecasting"
        elif any(word in keywords for word in ["compare", "benchmark", "versus", "against"]):
            return "comparison"
        else:
            return "informational"
    
    def _identify_relevant_domains(self, query_analysis: Dict) -> List[str]:
        """Identify which dashboard domains are most relevant to the query"""
        domain_scores = {}
        keywords = query_analysis.get("keywords", [])
        
        for domain_id, domain_config in self.dashboard_domains.items():
            score = 0
            
            # Score based on keyword matches
            for keyword in keywords:
                if keyword in domain_config["keywords"]:
                    score += 2  # High relevance
                elif any(domain_keyword in keyword or keyword in domain_keyword 
                        for domain_keyword in domain_config["keywords"]):
                    score += 1  # Partial relevance
            
            # Apply domain weight
            score *= domain_config["weight"]
            
            if score > 0:
                domain_scores[domain_id] = score
        
        # Sort by score and return top domains
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        return [domain_id for domain_id, score in sorted_domains if score > 0]
    
    def _search_domain(self, domain_id: str, query_analysis: Dict, 
                       filters: Dict = None) -> Dict[str, Any]:
        """Search within a specific dashboard domain"""
        try:
            domain_results = {
                "domain_id": domain_id,
                "domain_name": self.dashboard_domains[domain_id]["name"],
                "results": [],
                "total_matches": 0
            }
            
            # Get domain data (this would normally call the specific intelligence module)
            domain_data = self._get_domain_data(domain_id, filters)
            
            if not domain_data:
                return domain_results
            
            # Search within domain data
            matches = self._search_domain_data(domain_data, query_analysis)
            
            # Format results
            formatted_results = []
            for match in matches:
                formatted_result = {
                    "id": match.get("id", ""),
                    "title": match.get("title", ""),
                    "content": match.get("content", ""),
                    "category": self._categorize_result(match),
                    "relevance_score": match.get("score", 0),
                    "data_type": match.get("data_type", "text"),
                    "source_path": f"{domain_id}.{match.get('source', '')}",
                    "navigation_url": self._generate_navigation_url(domain_id, match),
                    "preview": self._generate_result_preview(match),
                    "metadata": {
                        "domain": domain_id,
                        "last_updated": match.get("last_updated"),
                        "data_quality": match.get("data_quality", "good")
                    }
                }
                formatted_results.append(formatted_result)
            
            domain_results["results"] = formatted_results
            domain_results["total_matches"] = len(formatted_results)
            
            return domain_results
            
        except Exception as e:
            logger.error(f"Error searching domain {domain_id}: {e}")
            return {"domain_id": domain_id, "results": [], "total_matches": 0}
    
    def _get_domain_data(self, domain_id: str, filters: Dict = None) -> Dict[str, Any]:
        """Get data for a specific domain by calling the real intelligence module.

        Previously returned hardcoded constants for "budget"/"hr" and {} for
        every other domain ("simplified simulation"). Each branch below calls
        the same class/function its own domain's overview API endpoint uses,
        so results match what a user sees on that domain's own dashboard.
        See plan-eng-review D3.5.
        """
        try:
            if domain_id == "executive":
                from insights.ml.executive_intelligence import ExecutiveIntelligence
                return ExecutiveIntelligence().get_executive_summary("YTD")

            if domain_id == "financial":
                from insights.ml.financial_intelligence import FinancialIntelligence
                return FinancialIntelligence().predict()

            if domain_id == "budget":
                from insights.ml.budget_variance_intelligence import BudgetVarianceIntelligence
                return BudgetVarianceIntelligence().get_budget_variance_overview()

            if domain_id == "hr":
                from insights.ml.hr_intelligence import HRIntelligence
                return HRIntelligence().get_hr_overview("YTD")

            if domain_id == "manufacturing":
                from insights.ml.manufacturing_intelligence import get_manufacturing_overview
                return get_manufacturing_overview(period="YTD")

            if domain_id == "sales":
                from insights.ml.sales_intelligence import SalesIntelligence
                return SalesIntelligence().predict()

            if domain_id == "customer":
                from insights.ml.customer_intelligence import CustomerIntelligence
                return CustomerIntelligence().predict()

            if domain_id == "esg":
                # ESG intelligence is disabled — see plan-eng-review D3.1.
                return {"status": "not_implemented"}

            # Unknown domain
            return {}

        except Exception as e:
            logger.error(f"Error getting domain data for {domain_id}: {e}")
            return {}
    
    def _search_domain_data(self, domain_data: Dict, query_analysis: Dict) -> List[Dict[str, Any]]:
        """Search within domain data structure"""
        matches = []
        keywords = query_analysis.get("keywords", [])
        
        try:
            # Search in different data sections
            for section_key, section_data in domain_data.items():
                if isinstance(section_data, dict):
                    # Search in dictionary values
                    for key, value in section_data.items():
                        if self._matches_search_criteria(str(value), keywords, key):
                            matches.append({
                                "id": f"{section_key}_{key}",
                                "title": key.replace("_", " ").title(),
                                "content": str(value),
                                "score": self._calculate_relevance_score(str(value), keywords),
                                "source": section_key,
                                "data_type": "metric" if isinstance(value, (int, float)) else "text"
                            })
                
                elif isinstance(section_data, list):
                    # Search in list items
                    for i, item in enumerate(section_data):
                        if isinstance(item, dict):
                            item_text = " ".join(str(v) for v in item.values())
                            if self._matches_search_criteria(item_text, keywords):
                                matches.append({
                                    "id": f"{section_key}_{i}",
                                    "title": item.get("title", f"{section_key} Item {i+1}"),
                                    "content": item_text,
                                    "score": self._calculate_relevance_score(item_text, keywords),
                                    "source": section_key,
                                    "data_type": "object"
                                })
            
            # Sort by relevance score
            matches.sort(key=lambda x: x.get("score", 0), reverse=True)
            return matches[:10]  # Limit to top 10 matches per domain
            
        except Exception as e:
            logger.error(f"Error searching domain data: {e}")
            return []
    
    def _matches_search_criteria(self, text: str, keywords: List[str], field_name: str = "") -> bool:
        """Check if text matches search criteria"""
        text_lower = text.lower()
        field_lower = field_name.lower()
        
        # Check for keyword matches in text or field name
        for keyword in keywords:
            if keyword in text_lower or keyword in field_lower:
                return True
        
        return False
    
    def _calculate_relevance_score(self, text: str, keywords: List[str]) -> float:
        """Calculate relevance score for search match"""
        if not keywords:
            return 0.0
        
        text_lower = text.lower()
        score = 0.0
        
        for keyword in keywords:
            # Exact match
            if keyword in text_lower:
                score += 2.0
            
            # Partial match
            elif any(keyword in word or word in keyword for word in text_lower.split()):
                score += 1.0
        
        # Normalize score
        return min(score / len(keywords), 10.0)
    
    def _categorize_result(self, result: Dict) -> str:
        """Categorize search result"""
        title_lower = result.get("title", "").lower()
        content_lower = result.get("content", "").lower()
        
        if any(word in title_lower for word in ["alert", "warning", "issue", "problem"]):
            return "alerts"
        elif any(word in title_lower for word in ["recommend", "suggestion", "improve"]):
            return "recommendations"
        elif any(word in title_lower for word in ["trend", "analysis", "over time"]):
            return "trends"
        elif any(word in title_lower for word in ["summary", "overview", "status"]):
            return "summary"
        elif any(word in title_lower for word in ["department", "division", "team"]):
            return "departmental"
        else:
            return "metrics"
    
    def _generate_navigation_url(self, domain_id: str, match: Dict) -> str:
        """Generate URL for navigating to the result"""
        base_url = f"/{domain_id.replace('_', '-')}-intelligence"
        
        # Add query parameters for context
        source = match.get("source", "")
        if source:
            return f"{base_url}?section={source}&highlight={match.get('id', '')}"
        
        return base_url
    
    def _generate_result_preview(self, match: Dict) -> str:
        """Generate preview text for search result"""
        content = match.get("content", "")
        
        # Limit preview length
        if len(content) > 150:
            return content[:147] + "..."
        
        return content
    
    def _aggregate_search_results(self, domain_results: Dict, 
                                  query_analysis: Dict) -> Dict[str, Any]:
        """Aggregate and organize results from all domains"""
        aggregated = {
            "by_category": defaultdict(list),
            "by_domain": domain_results,
            "top_results": [],
            "related_searches": []
        }
        
        # Collect all results
        all_results = []
        for domain_data in domain_results.values():
            for result in domain_data.get("results", []):
                all_results.append(result)
        
        # Sort by relevance score
        all_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        aggregated["top_results"] = all_results[:20]  # Top 20 overall
        
        # Categorize results
        for result in all_results:
            category = result.get("category", "metrics")
            aggregated["by_category"][category].append(result)
        
        # Generate related searches
        aggregated["related_searches"] = self._generate_related_searches(query_analysis)
        
        return aggregated
    
    def _generate_related_searches(self, query_analysis: Dict) -> List[str]:
        """Generate related search suggestions"""
        related = []
        keywords = query_analysis.get("keywords", [])
        query_intent = query_analysis.get("query_intent", "")
        
        # Intent-based suggestions
        if query_intent == "monitoring":
            related.extend([
                "performance trends",
                "key metrics dashboard",
                "status alerts"
            ])
        elif query_intent == "troubleshooting":
            related.extend([
                "critical issues",
                "system alerts",
                "performance problems"
            ])
        elif query_intent == "advisory":
            related.extend([
                "recommendations",
                "improvement suggestions",
                "optimization opportunities"
            ])
        
        # Keyword-based suggestions
        for keyword in keywords[:3]:  # Top 3 keywords
            related.append(f"{keyword} analysis")
            related.append(f"{keyword} trends")
        
        return related[:8]  # Limit to 8 suggestions
    
    def _generate_navigation_suggestions(self, query_analysis: Dict, 
                                         relevant_domains: List[str], 
                                         search_results: Dict) -> Dict[str, Any]:
        """Generate cross-dashboard navigation suggestions"""
        suggestions = {
            "quick_actions": [],
            "related_dashboards": [],
            "contextual_navigation": []
        }
        
        # Quick actions based on query intent
        query_intent = query_analysis.get("query_intent", "")
        if query_intent == "troubleshooting":
            suggestions["quick_actions"].extend([
                {"label": "View All Alerts", "action": "navigate", "target": "alerts_overview"},
                {"label": "System Health Check", "action": "navigate", "target": "system_health"},
                {"label": "Performance Monitor", "action": "navigate", "target": "performance_dashboard"}
            ])
        elif query_intent == "forecasting":
            suggestions["quick_actions"].extend([
                {"label": "Predictive Analytics", "action": "navigate", "target": "predictive_dashboard"},
                {"label": "Trend Analysis", "action": "navigate", "target": "trends_dashboard"},
                {"label": "Forecast Models", "action": "navigate", "target": "forecast_center"}
            ])
        
        # Related dashboards
        for domain_id in relevant_domains:
            domain_config = self.dashboard_domains[domain_id]
            suggestions["related_dashboards"].append({
                "id": domain_id,
                "name": domain_config["name"],
                "relevance": self._calculate_domain_relevance(domain_id, query_analysis),
                "url": f"/{domain_id.replace('_', '-')}-intelligence"
            })
        
        # Contextual navigation based on results
        top_categories = self._get_top_result_categories(search_results)
        for category in top_categories:
            if category in self.result_categories:
                cat_config = self.result_categories[category]
                suggestions["contextual_navigation"].append({
                    "category": category,
                    "label": f"View All {cat_config['label']}",
                    "icon": cat_config["icon"],
                    "action": "filter_results",
                    "filter": {"category": category}
                })
        
        return suggestions
    
    def _get_top_result_categories(self, search_results: Dict) -> List[str]:
        """Get top categories from search results"""
        category_counts = defaultdict(int)
        
        for result in search_results.get("top_results", []):
            category = result.get("category", "metrics")
            category_counts[category] += 1
        
        # Sort by count and return top categories
        sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
        return [category for category, count in sorted_categories[:5]]
    
    def _calculate_domain_relevance(self, domain_id: str, query_analysis: Dict) -> float:
        """Calculate relevance score for a domain"""
        if domain_id not in self.dashboard_domains:
            return 0.0
        
        domain_config = self.dashboard_domains[domain_id]
        keywords = query_analysis.get("keywords", [])
        
        score = 0.0
        for keyword in keywords:
            if keyword in domain_config["keywords"]:
                score += 2.0
            elif any(domain_keyword in keyword for domain_keyword in domain_config["keywords"]):
                score += 1.0
        
        # Apply domain weight
        score *= domain_config["weight"]
        
        # Normalize to 0-1 range
        return min(score / 10.0, 1.0)
    
    def _create_search_summary(self, query: str, total_results: int, 
                               relevant_domains: List[str], 
                               aggregated_results: Dict) -> Dict[str, Any]:
        """Create search summary"""
        summary = {
            "query": query,
            "total_results": total_results,
            "domains_searched": len(relevant_domains),
            "categories_found": len(aggregated_results.get("by_category", {})),
            "search_quality": "good",
            "response_time": "fast",
            "suggestions_available": len(aggregated_results.get("related_searches", []))
        }
        
        # Determine search quality
        if total_results == 0:
            summary["search_quality"] = "no_results"
        elif total_results < 5:
            summary["search_quality"] = "limited"
        elif total_results > 50:
            summary["search_quality"] = "extensive"
        
        return summary
    
    def _log_search_activity(self, search_session: Dict, results: Dict) -> None:
        """Log search activity for analytics"""
        try:
            # Create search log entry (simplified)
            log_entry = {
                "session_id": search_session["session_id"],
                "user": search_session["user"],
                "query": search_session["query"],
                "results_count": len(results.get("top_results", [])),
                "domains_searched": ",".join(results.get("by_domain", {}).keys()),
                "timestamp": search_session["timestamp"],
                "filters_used": json.dumps(search_session.get("filters", {}))
            }
            
            # In a real implementation, this would save to database
            logger.info(f"Search logged: {log_entry}")
            
        except Exception as e:
            logger.error(f"Error logging search activity: {e}")
    
    def _generate_query_suggestions(self, partial_query: str) -> List[Dict[str, Any]]:
        """Generate query-based suggestions"""
        suggestions = []
        partial_lower = partial_query.lower()
        
        # Common query patterns
        query_patterns = [
            "budget variance by department",
            "employee retention rate",
            "sales performance this quarter",
            "manufacturing efficiency trends",
            "customer satisfaction scores",
            "financial health overview",
            "ESG compliance status",
            "executive summary dashboard"
        ]
        
        for pattern in query_patterns:
            if partial_lower in pattern or pattern.startswith(partial_lower):
                suggestions.append({
                    "text": pattern,
                    "type": "query_completion",
                    "confidence": 0.8
                })
        
        return suggestions[:5]
    
    def _generate_context_suggestions(self, partial_query: str, context: Dict) -> List[Dict[str, Any]]:
        """Generate context-based suggestions"""
        suggestions = []
        
        # Current dashboard context
        current_dashboard = context.get("dashboard", "")
        if current_dashboard:
            domain_config = self.dashboard_domains.get(current_dashboard, {})
            for keyword in domain_config.get("keywords", []):
                if partial_query.lower() in keyword or keyword.startswith(partial_query.lower()):
                    suggestions.append({
                        "text": f"{keyword} in {domain_config.get('name', '')}",
                        "type": "context_suggestion",
                        "confidence": 0.7
                    })
        
        return suggestions[:3]
    
    def _get_popular_searches(self, partial_query: str) -> List[Dict[str, Any]]:
        """Get popular searches matching partial query"""
        # In a real implementation, this would query actual search analytics
        popular_queries = [
            "revenue trends",
            "budget status",
            "employee metrics",
            "performance dashboard",
            "alerts overview",
            "quarterly summary"
        ]
        
        suggestions = []
        partial_lower = partial_query.lower()
        
        for query in popular_queries:
            if partial_lower in query.lower() or query.lower().startswith(partial_lower):
                suggestions.append({
                    "text": query,
                    "type": "popular_search",
                    "confidence": 0.6
                })
        
        return suggestions[:3]
    
    def _get_recommended_navigation_action(self, current_context: Dict, 
                                           navigation_options: List[Dict]) -> Dict[str, Any]:
        """Get recommended navigation action"""
        if not navigation_options:
            return {"action": "stay", "reason": "No relevant dashboards found"}
        
        # Get highest confidence option
        best_option = max(navigation_options, key=lambda x: x.get("confidence", 0))
        
        if best_option["confidence"] > 0.7:
            return {
                "action": "navigate",
                "target": best_option,
                "reason": f"High relevance match for {best_option['domain_name']}"
            }
        elif best_option["confidence"] > 0.4:
            return {
                "action": "suggest",
                "target": best_option,
                "reason": f"Potential match in {best_option['domain_name']}"
            }
        else:
            return {
                "action": "stay",
                "reason": "Low confidence in cross-dashboard matches"
            }


# Service instance
cross_dashboard_search_service = CrossDashboardSearchService()