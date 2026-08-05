# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
import time
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import redis
import json
import hashlib


class ModelType(Enum):
    """Routing tiers for OpenRouter task dispatch.

    Values are OpenRouter model ids verified live (Aug 2026); the previous
    llama-3.1 / claude-3.5 ids were delisted upstream. Tier names are
    deliberately model-agnostic so a catalog refresh is a one-line change.
    """
    FAST = "nvidia/nemotron-3-nano-30b-a3b:free"
    BALANCED = "nvidia/nemotron-3-super-120b-a12b:free"
    PREMIUM = "anthropic/claude-haiku-4.5"


class TaskComplexity(Enum):
    """Task complexity levels for model routing"""
    SIMPLE = "simple"        # Quick queries, summaries
    MEDIUM = "medium"        # Multi-table analysis 
    COMPLEX = "complex"      # Forecasting, ML analysis


@dataclass
class ModelQuota:
    """Model usage quota configuration"""
    model: ModelType
    daily_limit: int
    current_usage: int
    percentage_allocation: float


@dataclass
class TaskRequest:
    """AI task request structure"""
    query: str
    complexity: TaskComplexity
    context: Dict[str, Any]
    user_id: str
    priority: int = 1
    timeout: int = 30


class AIModelRouter:
    """Intelligent AI model router with quota management and performance optimization"""
    
    def __init__(self):
        self.redis_client = self._get_redis_client()
        self.quotas = self._initialize_quotas()
        self.performance_cache = {}
        
    def _get_redis_client(self):
        """Get Redis client for caching and quota tracking"""
        try:
            redis_cache = frappe.cache()
            return redis_cache
        except Exception:
            # Fallback to in-memory cache if Redis unavailable
            frappe.log_error("Redis unavailable, using fallback cache")
            return None
    
    def _initialize_quotas(self) -> Dict[ModelType, ModelQuota]:
        """Initialize balanced model quotas - 70% 8B, 25% 70B, 5% Haiku"""
        daily_total = frappe.db.get_single_value("Insights Settings", "daily_ai_quota") or 1000
        
        return {
            ModelType.FAST: ModelQuota(
                model=ModelType.FAST,
                daily_limit=int(daily_total * 0.70),
                current_usage=self._get_current_usage(ModelType.FAST),
                percentage_allocation=70.0
            ),
            ModelType.BALANCED: ModelQuota(
                model=ModelType.BALANCED, 
                daily_limit=int(daily_total * 0.25),
                current_usage=self._get_current_usage(ModelType.BALANCED),
                percentage_allocation=25.0
            ),
            ModelType.PREMIUM: ModelQuota(
                model=ModelType.PREMIUM,
                daily_limit=int(daily_total * 0.05),
                current_usage=self._get_current_usage(ModelType.PREMIUM),
                percentage_allocation=5.0
            )
        }
    
    def _get_current_usage(self, model: ModelType) -> int:
        """Get current daily usage for a model"""
        cache_key = f"ai_usage:{model.value}:{datetime.now().strftime('%Y-%m-%d')}"
        
        if self.redis_client:
            usage = self.redis_client.get(cache_key)
            return int(usage) if usage else 0
        else:
            # Fallback to database
            return frappe.db.count("AI Usage Log", {
                "model": model.value,
                "creation": [">=", datetime.now().replace(hour=0, minute=0, second=0)]
            })
    
    def route_request(self, task: TaskRequest) -> Dict[str, Any]:
        """Route AI request to optimal model based on complexity and quotas"""
        
        # Check cache first for identical requests
        cache_result = self._check_cache(task)
        if cache_result:
            return cache_result
        
        # Determine optimal model
        optimal_model = self._select_model(task)
        
        # Check quota availability
        if not self._check_quota(optimal_model):
            optimal_model = self._get_fallback_model(task.complexity)
        
        # Execute request
        try:
            start_time = time.time()
            result = self._execute_request(task, optimal_model)
            response_time = time.time() - start_time
            
            # Update usage tracking
            self._update_usage(optimal_model, response_time)
            
            # Cache successful results
            self._cache_result(task, result)
            
            return {
                "success": True,
                "result": result,
                "model_used": optimal_model.value,
                "response_time": response_time,
                "cached": False
            }
            
        except Exception as e:
            frappe.log_error(f"AI Request failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "model_used": optimal_model.value
            }
    
    def _select_model(self, task: TaskRequest) -> ModelType:
        """Select optimal model based on task complexity and performance"""
        
        complexity_mapping = {
            TaskComplexity.SIMPLE: ModelType.FAST,
            TaskComplexity.MEDIUM: ModelType.FAST,
            TaskComplexity.COMPLEX: ModelType.BALANCED
        }
        
        # Default model selection
        selected_model = complexity_mapping.get(task.complexity, ModelType.FAST)
        
        # Override for specific patterns
        query_lower = task.query.lower()
        
        # Complex analysis keywords -> use 70B model
        complex_keywords = [
            "forecast", "predict", "trend analysis", "correlation", 
            "machine learning", "statistical", "regression", "clustering"
        ]
        if any(keyword in query_lower for keyword in complex_keywords):
            selected_model = ModelType.BALANCED
        
        # Simple parsing tasks -> use Haiku
        simple_keywords = [
            "parse", "extract", "classify", "summarize", "translate"
        ]
        if any(keyword in query_lower for keyword in simple_keywords):
            selected_model = ModelType.PREMIUM
            
        return selected_model
    
    def _check_quota(self, model: ModelType) -> bool:
        """Check if model has available quota"""
        quota = self.quotas[model]
        return quota.current_usage < quota.daily_limit
    
    def _get_fallback_model(self, complexity: TaskComplexity) -> ModelType:
        """Get fallback model when primary choice unavailable"""
        # Try models in order of availability
        for model in [ModelType.FAST, ModelType.PREMIUM, ModelType.BALANCED]:
            if self._check_quota(model):
                return model
        
        # If all quotas exhausted, use the FAST tier (most generous quota)
        return ModelType.FAST
    
    def _execute_request(self, task: TaskRequest, model: ModelType) -> str:
        """Execute AI request with selected model"""
        from insights.ai.provider_factory import AIProviderFactory

        client = AIProviderFactory.get_client()
        
        # Optimize prompt based on model capabilities
        optimized_prompt = self._optimize_prompt(task.query, model, task.context)
        
        response = client.query(
            prompt=optimized_prompt,
            model=model.value,
            max_tokens=self._get_max_tokens(model),
            temperature=0.1 if task.complexity == TaskComplexity.COMPLEX else 0.3
        )
        
        return response
    
    def _optimize_prompt(self, query: str, model: ModelType, context: Dict[str, Any]) -> str:
        """Optimize prompt based on model capabilities"""
        
        base_prompt = f"""You are an expert business intelligence analyst for ERPNext ERP system. 
        
User Query: {query}

Context: {json.dumps(context, indent=2) if context else 'No additional context'}

Instructions:
- Provide accurate, actionable business insights
- Use data-driven reasoning
- Format responses clearly with bullet points where appropriate
- Focus on ERPNext business processes and metrics

Response:"""

        # Model-specific optimizations
        if model == ModelType.BALANCED:
            # Complex analysis prompt
            return f"""{base_prompt}

Perform deep analysis with:
1. Statistical insights and trends
2. Predictive recommendations  
3. Risk assessment and opportunities
4. Quantitative metrics and KPIs

Detailed Analysis:"""

        elif model == ModelType.PREMIUM:
            # Fast parsing prompt
            return f"""Parse and extract key information:

Query: {query}
Context: {context}

Provide concise, structured response:"""

        else:  # FAST
            # Balanced analysis prompt
            return base_prompt
    
    def _get_max_tokens(self, model: ModelType) -> int:
        """Get optimal max tokens for each model"""
        token_limits = {
            ModelType.FAST: 2000,
            ModelType.BALANCED: 4000,
            ModelType.PREMIUM: 1000
        }
        return token_limits.get(model, 2000)
    
    def _check_cache(self, task: TaskRequest) -> Optional[Dict[str, Any]]:
        """Check if request result is cached (delegates to central CacheManager)"""
        from insights.cache_management.cache_manager import get_cached_data
        cache_key = self._generate_cache_key(task)
        cached_result = get_cached_data(cache_key)
        if cached_result:
            cached_result["cached"] = True
            return cached_result
        return None
    
    def _cache_result(self, task: TaskRequest, result: str):
        """Cache successful AI result (delegates to central CacheManager)"""
        from insights.cache_management.cache_manager import cache_data
        cache_key = self._generate_cache_key(task)
        cache_payload = {
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "complexity": task.complexity.value
        }
        # Cache duration based on complexity
        ttl_map = {
            TaskComplexity.SIMPLE: 86400,   # 24 h
            TaskComplexity.MEDIUM: 43200,   # 12 h
            TaskComplexity.COMPLEX: 21600   #  6 h
        }
        cache_data(cache_key, cache_payload, level="hot", ttl=ttl_map.get(task.complexity, 43200))
    
    def _generate_cache_key(self, task: TaskRequest) -> str:
        """Generate cache key for task"""
        key_data = f"{task.query}:{task.complexity.value}:{json.dumps(task.context, sort_keys=True)}"
        return f"ai_cache:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    def _update_usage(self, model: ModelType, response_time: float):
        """Update model usage statistics"""
        # Update quota counter
        cache_key = f"ai_usage:{model.value}:{datetime.now().strftime('%Y-%m-%d')}"
        
        if self.redis_client:
            self.redis_client.incr(cache_key)
            self.redis_client.expire(cache_key, 86400)  # 24 hours
        
        # Log usage for analytics
        usage_log = frappe.get_doc({
            "doctype": "AI Usage Log",
            "model": model.value,
            "response_time": response_time,
            "user": frappe.session.user,
            "timestamp": datetime.now()
        })
        usage_log.insert(ignore_permissions=True)
        
        # Update in-memory quota
        self.quotas[model].current_usage += 1
    
    def get_quota_status(self) -> Dict[str, Any]:
        """Get current quota status for monitoring"""
        status = {}
        for model_type, quota in self.quotas.items():
            status[model_type.value] = {
                "current_usage": quota.current_usage,
                "daily_limit": quota.daily_limit,
                "percentage_used": (quota.current_usage / quota.daily_limit) * 100,
                "allocation_percentage": quota.percentage_allocation
            }
        
        return status
    
    def reset_daily_quotas(self):
        """Reset daily quotas (called by scheduler)"""
        for model_type in self.quotas:
            self.quotas[model_type].current_usage = 0
        
        frappe.db.commit()


# Convenience functions for external use
def route_ai_request(query: str, complexity: str = "medium", context: Dict[str, Any] = None, user_id: str = None) -> Dict[str, Any]:
    """Route AI request through the model router"""
    router = AIModelRouter()
    
    task = TaskRequest(
        query=query,
        complexity=TaskComplexity(complexity),
        context=context or {},
        user_id=user_id or frappe.session.user
    )
    
    return router.route_request(task)


def get_model_status() -> Dict[str, Any]:
    """Get current model quota status"""
    router = AIModelRouter()
    return router.get_quota_status()


def analyze_query_complexity(query: str, context: Dict[str, Any] = None) -> TaskComplexity:
    """Analyze query complexity for optimal model selection"""
    query_lower = query.lower()
    
    # Complex analysis indicators
    complex_indicators = [
        "forecast", "predict", "trend", "correlation", "regression",
        "machine learning", "statistical", "clustering", "optimization",
        "multiple years", "historical analysis", "what if"
    ]
    
    # Simple query indicators  
    simple_indicators = [
        "show me", "list", "count", "total", "sum", "average",
        "who", "what", "when", "where", "latest", "recent"
    ]
    
    complex_count = sum(1 for indicator in complex_indicators if indicator in query_lower)
    simple_count = sum(1 for indicator in simple_indicators if indicator in query_lower)
    
    # Context complexity factors
    context_complexity = 0
    if context:
        # Multiple tables/doctypes increase complexity
        if isinstance(context.get('tables'), list) and len(context.get('tables', [])) > 3:
            context_complexity += 1
        # Large date ranges increase complexity
        if 'date_range' in context and context.get('days', 0) > 365:
            context_complexity += 1
    
    # Determine complexity
    if complex_count > 1 or context_complexity > 1:
        return TaskComplexity.COMPLEX
    elif simple_count > complex_count and context_complexity == 0:
        return TaskComplexity.SIMPLE
    else:
        return TaskComplexity.MEDIUM