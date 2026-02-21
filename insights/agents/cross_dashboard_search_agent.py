"""
Cross-Dashboard Search Agent

Intelligent agent for handling cross-dashboard search queries and navigation.
Provides conversational search capabilities, smart routing, and contextual assistance.

Features:
- Natural language query processing
- Intelligent search routing across domains
- Contextual query understanding
- Search result interpretation and explanation
- Cross-dashboard navigation assistance
- Search personalization and learning

Author: AI Assistant
Version: 1.0.0
"""

import frappe
from typing import Dict, List, Any, Optional
import json
import logging
from datetime import datetime

# Import our search service
from insights.ml.cross_dashboard_search import cross_dashboard_search_service

logger = logging.getLogger(__name__)

class CrossDashboardSearchAgent:
    """
    Intelligent agent for cross-dashboard search and navigation
    
    Handles natural language queries, provides contextual search results,
    and assists with cross-dashboard navigation and data discovery.
    """
    
    def __init__(self):
        self.agent_name = "Cross-Dashboard Search Agent"
        self.agent_type = "search_navigation"
        self.search_service = cross_dashboard_search_service
        
        # Query classification patterns
        self.query_patterns = {
            "search": ["search", "find", "look for", "show me", "what is", "where is"],
            "navigation": ["go to", "navigate", "switch to", "open", "take me to"],
            "comparison": ["compare", "vs", "versus", "difference", "better", "worse"],
            "analysis": ["analyze", "explain", "why", "how", "what caused", "trends"],
            "help": ["help", "how to", "guide", "tutorial", "explain", "what can"]
        }
        
        # Response templates
        self.response_templates = {
            "search_results": "I found {count} results for '{query}' across {domains} dashboards:",
            "no_results": "I couldn't find any results for '{query}'. Let me suggest some alternatives:",
            "navigation_suggestion": "Based on your query, I recommend navigating to the {dashboard} dashboard:",
            "search_help": "I can help you search across all intelligence dashboards. Try queries like:",
            "clarification": "I need a bit more information. Are you looking for:"
        }
    
    def can_handle_query(self, query: str, context: Dict = None) -> bool:
        """
        Determine if this agent can handle the given query
        
        Args:
            query: User query string
            context: Query context
            
        Returns:
            Boolean indicating if agent can handle the query
        """
        try:
            query_lower = query.lower()
            
            # Check for search-related keywords
            search_indicators = [
                "search", "find", "look", "show", "where", "what", "how",
                "navigate", "go to", "dashboard", "data", "information"
            ]
            
            # Check for cross-dashboard terms
            cross_dashboard_terms = [
                "across", "all", "compare", "overview", "summary", 
                "everywhere", "global", "comprehensive"
            ]
            
            # Agent can handle if query contains search indicators
            if any(indicator in query_lower for indicator in search_indicators):
                return True
            
            # Also handle cross-dashboard navigation queries
            if any(term in query_lower for term in cross_dashboard_terms):
                return True
            
            # Handle if context suggests search/navigation
            if context and context.get("intent") in ["search", "navigation", "discovery"]:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error in can_handle_query: {e}")
            return False
    
    def get_insights(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """
        Process search query and return intelligent insights
        
        Args:
            query: Search query string
            context: Query context and user state
            
        Returns:
            Comprehensive search insights and navigation assistance
        """
        try:
            logger.info(f"Processing cross-dashboard search query: {query}")
            
            # Classify query type
            query_type = self._classify_query(query)
            
            # Handle different query types
            if query_type == "help":
                return self._provide_search_help(query, context)
            elif query_type == "navigation":
                return self._handle_navigation_query(query, context)
            elif query_type == "comparison":
                return self._handle_comparison_query(query, context)
            elif query_type == "search":
                return self._handle_search_query(query, context)
            else:
                # Default to search
                return self._handle_search_query(query, context)
            
        except Exception as e:
            logger.error(f"Error processing search query: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "I encountered an error while processing your search. Please try again."
            }
    
    def _classify_query(self, query: str) -> str:
        """Classify the type of query"""
        query_lower = query.lower()
        
        for query_type, patterns in self.query_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                return query_type
        
        return "search"  # Default to search
    
    def _handle_search_query(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Handle search-specific queries"""
        try:
            # Perform global search
            search_results = self.search_service.perform_global_search(
                query=query,
                filters=context.get("filters") if context else None,
                user_context=context
            )
            
            # Generate conversational response
            response = self._generate_search_response(query, search_results)
            
            # Add search suggestions
            suggestions = self.search_service.get_search_suggestions(
                query, context
            )
            
            # Prepare agent insights
            insights = {
                "success": True,
                "agent_response": response,
                "search_results": search_results,
                "suggestions": suggestions,
                "query_type": "search",
                "conversation_context": {
                    "last_query": query,
                    "search_session": search_results.get("search_session"),
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Add navigation recommendations if results are limited
            if search_results.get("total_results", 0) < 3:
                navigation_recs = self._suggest_alternative_navigation(query, context)
                insights["navigation_recommendations"] = navigation_recs
            
            return insights
            
        except Exception as e:
            logger.error(f"Error handling search query: {e}")
            return {
                "success": False,
                "message": "I had trouble searching across the dashboards. Please try rephrasing your query."
            }
    
    def _handle_navigation_query(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Handle navigation-specific queries"""
        try:
            # Get navigation suggestions
            navigation_data = self.search_service.get_cross_dashboard_navigation(
                current_context=context or {},
                target_query=query
            )
            
            # Generate navigation response
            response = self._generate_navigation_response(query, navigation_data)
            
            return {
                "success": True,
                "agent_response": response,
                "navigation_data": navigation_data,
                "query_type": "navigation",
                "action": "navigate"
            }
            
        except Exception as e:
            logger.error(f"Error handling navigation query: {e}")
            return {
                "success": False,
                "message": "I couldn't determine the best navigation path. Can you be more specific about which dashboard you want to visit?"
            }
    
    def _handle_comparison_query(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Handle comparison queries across dashboards"""
        try:
            # Extract comparison entities from query
            comparison_entities = self._extract_comparison_entities(query)
            
            # Perform searches for each entity
            comparison_results = {}
            for entity in comparison_entities:
                search_result = self.search_service.perform_global_search(
                    query=entity,
                    filters=context.get("filters") if context else None,
                    user_context=context
                )
                comparison_results[entity] = search_result
            
            # Generate comparison insights
            response = self._generate_comparison_response(query, comparison_results)
            
            return {
                "success": True,
                "agent_response": response,
                "comparison_data": comparison_results,
                "query_type": "comparison",
                "entities": comparison_entities
            }
            
        except Exception as e:
            logger.error(f"Error handling comparison query: {e}")
            return {
                "success": False,
                "message": "I had trouble comparing those items. Could you specify what you'd like to compare?"
            }
    
    def _provide_search_help(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Provide search help and guidance"""
        help_content = {
            "message": "I can help you search across all intelligence dashboards. Here's what I can do:",
            "capabilities": [
                "🔍 Search for specific metrics, alerts, or insights",
                "📊 Find data across Executive, Financial, HR, and other dashboards",
                "🚀 Navigate between different intelligence modules",
                "📈 Compare metrics across different departments or time periods",
                "💡 Provide recommendations based on your queries",
                "⭐ Save your favorite searches for quick access"
            ],
            "sample_queries": [
                "Show me budget variance alerts",
                "Find HR retention metrics",
                "Compare sales performance across regions",
                "What are the key executive insights?",
                "Show me ESG compliance status"
            ],
            "tips": [
                "Use natural language - ask me questions like you would a colleague",
                "Be specific about time periods (this month, last quarter, etc.)",
                "Mention departments or areas you're interested in",
                "Ask for comparisons between different metrics or periods"
            ]
        }
        
        return {
            "success": True,
            "agent_response": "I'm here to help you navigate and search across all your business intelligence dashboards!",
            "help_content": help_content,
            "query_type": "help"
        }
    
    def _extract_comparison_entities(self, query: str) -> List[str]:
        """Extract entities to compare from query"""
        entities = []
        query_lower = query.lower()
        
        # Simple extraction patterns
        if " vs " in query_lower:
            parts = query_lower.split(" vs ")
            entities.extend([part.strip() for part in parts])
        elif " versus " in query_lower:
            parts = query_lower.split(" versus ")
            entities.extend([part.strip() for part in parts])
        elif " and " in query_lower and "compare" in query_lower:
            # Extract items around "and"
            compare_part = query_lower.split("compare")[1] if "compare" in query_lower else query_lower
            if " and " in compare_part:
                parts = compare_part.split(" and ")
                entities.extend([part.strip() for part in parts])
        
        # Clean up entities
        cleaned_entities = []
        for entity in entities:
            # Remove common words
            entity = entity.replace("the", "").replace("our", "").strip()
            if len(entity) > 2:
                cleaned_entities.append(entity)
        
        return cleaned_entities[:4]  # Limit to 4 entities
    
    def _generate_search_response(self, query: str, search_results: Dict) -> str:
        """Generate conversational response for search results"""
        try:
            total_results = search_results.get("total_results", 0)
            
            if total_results == 0:
                return self.response_templates["no_results"].format(query=query)
            
            # Get domain information
            domains_searched = list(search_results.get("results", {}).get("by_domain", {}).keys())
            domain_names = []
            for domain_id in domains_searched:
                if domain_id in self.search_service.dashboard_domains:
                    domain_names.append(self.search_service.dashboard_domains[domain_id]["name"])
            
            response = self.response_templates["search_results"].format(
                count=total_results,
                query=query,
                domains=", ".join(domain_names) if domain_names else "multiple"
            )
            
            # Add summary of key findings
            top_results = search_results.get("results", {}).get("top_results", [])
            if top_results:
                response += "\n\nKey findings:"
                for i, result in enumerate(top_results[:3]):
                    response += f"\n• {result.get('title', 'Untitled')}: {result.get('preview', '')}"
            
            # Add navigation suggestion if applicable
            navigation = search_results.get("navigation", {})
            related_dashboards = navigation.get("related_dashboards", [])
            if related_dashboards:
                best_dashboard = related_dashboards[0]
                response += f"\n\nFor more details, you might want to explore the {best_dashboard.get('name', 'related')} dashboard."
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating search response: {e}")
            return f"I found {total_results} results for your query."
    
    def _generate_navigation_response(self, query: str, navigation_data: Dict) -> str:
        """Generate response for navigation queries"""
        try:
            navigation_options = navigation_data.get("navigation_options", [])
            
            if not navigation_options:
                return "I couldn't find a specific dashboard for your request. Could you be more specific?"
            
            best_option = navigation_options[0]
            confidence = best_option.get("confidence", 0)
            
            if confidence > 0.7:
                return f"I recommend navigating to the {best_option['domain_name']} dashboard. It's the best match for your query."
            elif confidence > 0.4:
                return f"You might find what you're looking for in the {best_option['domain_name']} dashboard. Would you like me to take you there?"
            else:
                dashboard_list = ", ".join([opt["domain_name"] for opt in navigation_options[:3]])
                return f"I found several relevant dashboards: {dashboard_list}. Which one interests you most?"
            
        except Exception as e:
            logger.error(f"Error generating navigation response: {e}")
            return "I can help you navigate to the right dashboard. What specific area are you interested in?"
    
    def _generate_comparison_response(self, query: str, comparison_results: Dict) -> str:
        """Generate response for comparison queries"""
        try:
            entities = list(comparison_results.keys())
            
            if len(entities) < 2:
                return "I need at least two items to compare. Could you rephrase your comparison request?"
            
            response = f"I compared {' and '.join(entities)} across all dashboards:\n"
            
            for entity, results in comparison_results.items():
                total_results = results.get("total_results", 0)
                response += f"\n• {entity.title()}: Found {total_results} relevant items"
                
                # Add top result for each entity
                top_results = results.get("results", {}).get("top_results", [])
                if top_results:
                    response += f" - Key finding: {top_results[0].get('title', 'Data available')}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating comparison response: {e}")
            return "I completed the comparison analysis across multiple dashboards."
    
    def _suggest_alternative_navigation(self, query: str, context: Dict = None) -> Dict[str, Any]:
        """Suggest alternative navigation when search results are limited"""
        try:
            # Analyze query to suggest relevant dashboards
            query_analysis = self.search_service._analyze_search_query(query)
            relevant_domains = self.search_service._identify_relevant_domains(query_analysis)
            
            suggestions = []
            for domain_id in relevant_domains[:3]:
                if domain_id in self.search_service.dashboard_domains:
                    domain = self.search_service.dashboard_domains[domain_id]
                    suggestions.append({
                        "dashboard_name": domain["name"],
                        "url": f"/{domain_id.replace('_', '-')}-intelligence",
                        "reason": f"Contains {', '.join(domain['keywords'][:3])} related data"
                    })
            
            return {
                "message": "You might find more relevant information in these dashboards:",
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error suggesting alternative navigation: {e}")
            return {
                "message": "Try exploring our intelligence dashboards for more insights.",
                "suggestions": []
            }


# Agent instance
cross_dashboard_search_agent = CrossDashboardSearchAgent()