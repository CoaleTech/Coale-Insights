# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from typing import Dict, Any, List, Optional, Callable
import asyncio
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue, PriorityQueue
from dataclasses import dataclass
from enum import Enum


class OptimizationLevel(Enum):
    """Performance optimization levels"""
    AGGRESSIVE = "aggressive"  # Maximum performance, higher resource usage
    BALANCED = "balanced"      # Balance between performance and resources
    CONSERVATIVE = "conservative"  # Minimal resource usage, slower processing


class PipelineStage(Enum):
    """Pipeline processing stages"""
    VALIDATION = "validation"
    PREPROCESSING = "preprocessing"
    EXECUTION = "execution"
    POSTPROCESSING = "postprocessing"
    DELIVERY = "delivery"


@dataclass
class PerformanceMetrics:
    """Performance metrics tracking"""
    request_count: int = 0
    total_processing_time: float = 0.0
    average_response_time: float = 0.0
    cache_hit_rate: float = 0.0
    error_rate: float = 0.0
    throughput: float = 0.0
    peak_concurrent_requests: int = 0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0


class PerformancePipeline:
    """Advanced performance optimization pipeline for AI insights processing"""
    
    def __init__(self, optimization_level: OptimizationLevel = OptimizationLevel.BALANCED):
        self.optimization_level = optimization_level
        self.executor = ThreadPoolExecutor(max_workers=self._get_max_workers())
        self.async_queue = PriorityQueue()
        self.batch_queue = Queue()
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.active_requests = {}
        self.performance_history = []
        
        # Pipeline configuration
        self.pipeline_config = self._initialize_pipeline_config()
        
        # Optimization features
        self.result_streaming = True
        self.progressive_loading = True
        self.smart_batching = True
        self.adaptive_caching = True
        
        # Monitoring thread is deferred — only started on first optimize_request()
        self._monitoring_started = False
    
    def _get_max_workers(self) -> int:
        """Get optimal number of worker threads based on optimization level"""
        
        if self.optimization_level == OptimizationLevel.AGGRESSIVE:
            return min(32, (os.cpu_count() or 4) * 4)
        elif self.optimization_level == OptimizationLevel.BALANCED:
            return min(16, (os.cpu_count() or 4) * 2)
        else:  # CONSERVATIVE
            return min(8, os.cpu_count() or 4)
    
    def _initialize_pipeline_config(self) -> Dict[str, Any]:
        """Initialize pipeline configuration based on optimization level"""
        
        if self.optimization_level == OptimizationLevel.AGGRESSIVE:
            return {
                "batch_size": 100,
                "max_concurrent": 50,
                "cache_strategy": "aggressive",
                "streaming_threshold": 1000,  # Stream results for queries > 1000 rows
                "progressive_chunks": 250,
                "timeout_multiplier": 2.0
            }
        elif self.optimization_level == OptimizationLevel.BALANCED:
            return {
                "batch_size": 50,
                "max_concurrent": 25,
                "cache_strategy": "smart",
                "streaming_threshold": 2000,
                "progressive_chunks": 500,
                "timeout_multiplier": 1.5
            }
        else:  # CONSERVATIVE
            return {
                "batch_size": 25,
                "max_concurrent": 10,
                "cache_strategy": "minimal",
                "streaming_threshold": 5000,
                "progressive_chunks": 1000,
                "timeout_multiplier": 1.0
            }
    
    def optimize_request(self, request_data: Dict[str, Any], 
                        callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Optimize and process request through performance pipeline"""
        
        # Lazy-start monitoring on first request
        self._start_performance_monitoring()
        
        request_id = frappe.generate_hash(length=12)
        start_time = time.time()
        
        try:
            # Track active request
            self.active_requests[request_id] = {
                "start_time": start_time,
                "stage": PipelineStage.VALIDATION,
                "callback": callback
            }
            
            # Stage 1: Validation and preprocessing
            validated_request = self._validate_and_preprocess(request_data, request_id)
            
            # Stage 2: Determine processing strategy
            processing_strategy = self._determine_processing_strategy(validated_request)
            
            # Stage 3: Execute with optimization
            if processing_strategy["type"] == "streaming":
                return self._execute_streaming(validated_request, request_id, callback)
            elif processing_strategy["type"] == "progressive":
                return self._execute_progressive(validated_request, request_id, callback)
            elif processing_strategy["type"] == "batch":
                return self._execute_batch(validated_request, request_id, callback)
            else:  # direct
                return self._execute_direct(validated_request, request_id)
                
        except Exception as e:
            self._handle_request_error(request_id, str(e))
            raise
        finally:
            # Cleanup and metrics
            self._finalize_request(request_id, start_time)
    
    def _validate_and_preprocess(self, request_data: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Validate and preprocess request for optimal performance"""
        
        self.active_requests[request_id]["stage"] = PipelineStage.PREPROCESSING
        
        # Extract key parameters
        query_type = request_data.get("type", "unknown")
        complexity = request_data.get("complexity", "medium")
        expected_rows = request_data.get("expected_rows", 1000)
        
        # Optimize query structure
        optimized_query = self._optimize_query_structure(request_data)
        
        # Add performance hints
        performance_hints = {
            "use_index_hints": complexity in ["medium", "complex"],
            "enable_query_cache": True,
            "prefer_covering_indexes": expected_rows > 10000,
            "use_materialized_views": complexity == "complex"
        }
        
        return {
            **optimized_query,
            "request_id": request_id,
            "performance_hints": performance_hints,
            "original_request": request_data
        }
    
    def _determine_processing_strategy(self, validated_request: Dict[str, Any]) -> Dict[str, Any]:
        """Determine optimal processing strategy"""
        
        expected_rows = validated_request.get("expected_rows", 1000)
        complexity = validated_request.get("complexity", "medium")
        user_preference = validated_request.get("user_preference", "balanced")
        
        # Streaming strategy for large datasets
        if expected_rows > self.pipeline_config["streaming_threshold"]:
            return {
                "type": "streaming",
                "chunk_size": min(1000, expected_rows // 10),
                "enable_compression": True
            }
        
        # Progressive loading for medium datasets
        elif expected_rows > self.pipeline_config["progressive_chunks"]:
            return {
                "type": "progressive", 
                "initial_load": self.pipeline_config["progressive_chunks"],
                "lazy_load_chunks": 500
            }
        
        # Batch processing for complex analysis
        elif complexity == "complex" and expected_rows > 100:
            return {
                "type": "batch",
                "batch_size": self.pipeline_config["batch_size"],
                "parallel_batches": min(4, self.pipeline_config["max_concurrent"])
            }
        
        # Direct processing for simple queries
        else:
            return {"type": "direct"}
    
    def _execute_streaming(self, request: Dict[str, Any], request_id: str, 
                          callback: Optional[Callable]) -> Dict[str, Any]:
        """Execute request with streaming results"""
        
        self.active_requests[request_id]["stage"] = PipelineStage.EXECUTION
        
        try:
            # Import query engine
            from insights.queries.streaming_engine import StreamingQueryEngine
            engine = StreamingQueryEngine()
            
            # Setup streaming response
            stream_config = {
                "chunk_size": request.get("chunk_size", 1000),
                "compression": request.get("enable_compression", False),
                "format": request.get("format", "json")
            }
            
            # Start streaming execution
            stream_handler = engine.execute_streaming_query(
                request["query_config"],
                stream_config,
                callback
            )
            
            return {
                "request_id": request_id,
                "type": "streaming",
                "stream_handler": stream_handler,
                "status": "streaming_started"
            }
            
        except Exception as e:
            frappe.log_error(f"Streaming execution failed: {str(e)}")
            raise
    
    def _execute_progressive(self, request: Dict[str, Any], request_id: str,
                           callback: Optional[Callable]) -> Dict[str, Any]:
        """Execute request with progressive loading"""
        
        self.active_requests[request_id]["stage"] = PipelineStage.EXECUTION
        
        try:
            # Import query engine
            from insights.queries.progressive_engine import ProgressiveQueryEngine
            engine = ProgressiveQueryEngine()
            
            # Initial data load
            initial_result = engine.execute_initial_load(
                request["query_config"],
                limit=request.get("initial_load", 500)
            )
            
            # Setup lazy loading for remaining data
            lazy_loader = engine.setup_lazy_loading(
                request["query_config"],
                offset=request.get("initial_load", 500),
                chunk_size=request.get("lazy_load_chunks", 500)
            )
            
            # Execute callback with initial data
            if callback:
                callback({
                    "request_id": request_id,
                    "type": "progressive",
                    "initial_data": initial_result,
                    "has_more": lazy_loader.has_more_data(),
                    "total_estimated": lazy_loader.get_total_estimate()
                })
            
            return {
                "request_id": request_id,
                "type": "progressive",
                "initial_data": initial_result,
                "lazy_loader": lazy_loader,
                "status": "initial_loaded"
            }
            
        except Exception as e:
            frappe.log_error(f"Progressive execution failed: {str(e)}")
            raise
    
    def _execute_batch(self, request: Dict[str, Any], request_id: str,
                      callback: Optional[Callable]) -> Dict[str, Any]:
        """Execute request with batch processing"""
        
        self.active_requests[request_id]["stage"] = PipelineStage.EXECUTION
        
        try:
            # Import batch engine
            from insights.queries.batch_engine import BatchQueryEngine
            engine = BatchQueryEngine()
            
            # Split query into batches
            batch_config = {
                "batch_size": request.get("batch_size", 50),
                "parallel_batches": request.get("parallel_batches", 4),
                "merge_strategy": "union"
            }
            
            # Execute batches in parallel
            batch_results = engine.execute_parallel_batches(
                request["query_config"],
                batch_config,
                callback
            )
            
            return {
                "request_id": request_id,
                "type": "batch",
                "batch_results": batch_results,
                "status": "batch_completed"
            }
            
        except Exception as e:
            frappe.log_error(f"Batch execution failed: {str(e)}")
            raise
    
    def _execute_direct(self, request: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Execute request directly without optimization"""
        
        self.active_requests[request_id]["stage"] = PipelineStage.EXECUTION
        
        try:
            # Import standard query engine
            from insights.queries.query_engine import QueryEngine
            engine = QueryEngine()
            
            # Execute query directly
            result = engine.execute_query(request["query_config"])
            
            self.active_requests[request_id]["stage"] = PipelineStage.DELIVERY
            
            return {
                "request_id": request_id,
                "type": "direct",
                "result": result,
                "status": "completed"
            }
            
        except Exception as e:
            frappe.log_error(f"Direct execution failed: {str(e)}")
            raise
    
    def _optimize_query_structure(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize query structure for better performance"""
        
        optimized = request_data.copy()
        
        # Add query optimizations based on structure
        query_config = optimized.get("query_config", {})
        
        # Optimize SELECT fields
        if "fields" in query_config:
            query_config["fields"] = self._optimize_field_selection(query_config["fields"])
        
        # Optimize WHERE conditions
        if "filters" in query_config:
            query_config["filters"] = self._optimize_filters(query_config["filters"])
        
        # Optimize ORDER BY
        if "order_by" in query_config:
            query_config["order_by"] = self._optimize_ordering(query_config["order_by"])
        
        # Add performance hints
        query_config["performance_hints"] = {
            "use_query_cache": True,
            "prefer_index_scans": True,
            "optimize_joins": True
        }
        
        optimized["query_config"] = query_config
        return optimized
    
    def _optimize_field_selection(self, fields: List[str]) -> List[str]:
        """Optimize field selection for better performance"""
        
        # Remove redundant fields and optimize order
        optimized_fields = []
        seen_fields = set()
        
        # Prioritize indexed fields first
        indexed_fields = self._get_indexed_fields()
        
        for field in fields:
            if field not in seen_fields:
                optimized_fields.append(field)
                seen_fields.add(field)
        
        return optimized_fields
    
    def _optimize_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize filter conditions for better performance"""
        
        optimized_filters = {}
        
        # Reorder filters for optimal execution
        # 1. Equality filters first (most selective)
        # 2. Range filters
        # 3. LIKE filters last
        
        filter_priority = {
            "=": 1,
            "!=": 2, 
            ">": 3,
            ">=": 3,
            "<": 3,
            "<=": 3,
            "in": 4,
            "not in": 5,
            "like": 6,
            "not like": 7
        }
        
        sorted_filters = sorted(
            filters.items(),
            key=lambda x: filter_priority.get(x[1].get("operator", "="), 8)
        )
        
        for field, condition in sorted_filters:
            optimized_filters[field] = condition
        
        return optimized_filters
    
    def _optimize_ordering(self, order_by: List[Dict]) -> List[Dict]:
        """Optimize ORDER BY clause for better performance"""
        
        # Prioritize indexed columns in ORDER BY
        indexed_fields = self._get_indexed_fields()
        
        optimized_order = []
        
        for order_spec in order_by:
            field = order_spec.get("field")
            if field in indexed_fields:
                optimized_order.insert(0, order_spec)  # Prioritize indexed fields
            else:
                optimized_order.append(order_spec)
        
        return optimized_order
    
    def _get_indexed_fields(self) -> List[str]:
        """Get list of indexed fields for optimization"""
        
        # This would be populated from database schema analysis
        # For now, return common ERPNext indexed fields
        return [
            "name", "creation", "modified", "owner", "docstatus",
            "company", "posting_date", "transaction_date", "customer",
            "supplier", "item_code", "warehouse"
        ]
    
    def _start_performance_monitoring(self):
        """Start background performance monitoring (lazy — only starts once).
        
        This is NOT called at import time to avoid spawning daemon threads
        in every Gunicorn worker on module import. Only starts when
        optimize_request() is actually called.
        """
        if self._monitoring_started:
            return
        self._monitoring_started = True
        
        def monitor_performance():
            while True:
                try:
                    # Update performance metrics
                    self._update_performance_metrics()
                    
                    # Check for performance issues
                    self._detect_performance_issues()
                    
                    # Optimize based on patterns
                    self._apply_adaptive_optimizations()
                    
                    time.sleep(30)  # Monitor every 30 seconds
                    
                except Exception as e:
                    frappe.log_error(f"Performance monitoring error: {str(e)}")
                    time.sleep(60)  # Longer pause on error
        
        # Start monitoring thread
        threading.Thread(target=monitor_performance, daemon=True).start()
    
    def _update_performance_metrics(self):
        """Update current performance metrics"""
        
        current_time = time.time()
        
        # Update request count and timing
        active_count = len(self.active_requests)
        self.metrics.peak_concurrent_requests = max(
            self.metrics.peak_concurrent_requests, 
            active_count
        )
        
        # Calculate throughput (requests per minute)
        if hasattr(self, '_last_throughput_check'):
            time_diff = current_time - self._last_throughput_check
            if time_diff >= 60:  # Update every minute
                completed_requests = self.metrics.request_count - getattr(self, '_last_request_count', 0)
                self.metrics.throughput = completed_requests / (time_diff / 60)
                self._last_request_count = self.metrics.request_count
                self._last_throughput_check = current_time
        else:
            self._last_throughput_check = current_time
            self._last_request_count = self.metrics.request_count
    
    def _detect_performance_issues(self):
        """Detect and alert on performance issues"""
        
        issues = []
        
        # High response time
        if self.metrics.average_response_time > 10.0:
            issues.append("High average response time detected")
        
        # Low cache hit rate
        if self.metrics.cache_hit_rate < 0.5:
            issues.append("Low cache hit rate detected")
        
        # High error rate
        if self.metrics.error_rate > 0.1:
            issues.append("High error rate detected")
        
        # High concurrent load
        if self.metrics.peak_concurrent_requests > self.pipeline_config["max_concurrent"] * 0.8:
            issues.append("High concurrent request load")
        
        # Log issues
        if issues:
            frappe.log_error(f"Performance issues detected: {', '.join(issues)}")
    
    def _apply_adaptive_optimizations(self):
        """Apply adaptive optimizations based on performance patterns"""
        
        # Adjust batch sizes based on performance
        if self.metrics.average_response_time > 5.0:
            # Reduce batch size for faster response
            self.pipeline_config["batch_size"] = max(10, self.pipeline_config["batch_size"] // 2)
        elif self.metrics.average_response_time < 1.0 and self.metrics.throughput > 50:
            # Increase batch size for higher throughput
            self.pipeline_config["batch_size"] = min(200, self.pipeline_config["batch_size"] * 2)
        
        # Adjust streaming thresholds
        if self.metrics.cache_hit_rate > 0.8:
            # Higher cache hits, can handle larger direct queries
            self.pipeline_config["streaming_threshold"] *= 1.2
        elif self.metrics.cache_hit_rate < 0.3:
            # Lower cache hits, stream earlier
            self.pipeline_config["streaming_threshold"] *= 0.8
    
    def _handle_request_error(self, request_id: str, error: str):
        """Handle request processing errors"""
        
        if request_id in self.active_requests:
            self.active_requests[request_id]["error"] = error
            self.active_requests[request_id]["stage"] = "failed"
        
        # Update error metrics
        self.metrics.error_rate = (
            (self.metrics.error_rate * self.metrics.request_count + 1) / 
            (self.metrics.request_count + 1)
        )
    
    def _finalize_request(self, request_id: str, start_time: float):
        """Finalize request and update metrics"""
        
        processing_time = time.time() - start_time
        
        # Update metrics
        self.metrics.request_count += 1
        self.metrics.total_processing_time += processing_time
        self.metrics.average_response_time = (
            self.metrics.total_processing_time / self.metrics.request_count
        )
        
        # Remove from active requests
        if request_id in self.active_requests:
            del self.active_requests[request_id]
        
        # Store performance history
        self.performance_history.append({
            "request_id": request_id,
            "processing_time": processing_time,
            "timestamp": datetime.now(),
            "optimization_level": self.optimization_level.value
        })
        
        # Keep only recent history (last 1000 requests)
        if len(self.performance_history) > 1000:
            self.performance_history = self.performance_history[-1000:]
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report"""
        
        return {
            "current_metrics": {
                "request_count": self.metrics.request_count,
                "average_response_time": self.metrics.average_response_time,
                "cache_hit_rate": self.metrics.cache_hit_rate,
                "error_rate": self.metrics.error_rate,
                "throughput": self.metrics.throughput,
                "peak_concurrent": self.metrics.peak_concurrent_requests
            },
            "active_requests": len(self.active_requests),
            "optimization_level": self.optimization_level.value,
            "pipeline_config": self.pipeline_config,
            "recent_performance": self.performance_history[-10:] if self.performance_history else []
        }
    
    def optimize_pipeline_config(self, target_metrics: Dict[str, float]):
        """Optimize pipeline configuration for target metrics"""
        
        # Adjust configuration based on target metrics
        if "response_time" in target_metrics:
            target_time = target_metrics["response_time"]
            if self.metrics.average_response_time > target_time:
                # Optimize for speed
                self.pipeline_config["batch_size"] //= 2
                self.pipeline_config["streaming_threshold"] //= 2
        
        if "throughput" in target_metrics:
            target_throughput = target_metrics["throughput"]
            if self.metrics.throughput < target_throughput:
                # Optimize for throughput
                self.pipeline_config["max_concurrent"] = min(
                    self.pipeline_config["max_concurrent"] * 2, 
                    100
                )


# Lazy global instance — no daemon thread spawned at import time
_performance_pipeline = None


def _get_pipeline() -> PerformancePipeline:
    """Get or create the global PerformancePipeline instance (lazy singleton)."""
    global _performance_pipeline
    if _performance_pipeline is None:
        _performance_pipeline = PerformancePipeline()
    return _performance_pipeline


# Backward-compatible attribute access
performance_pipeline = None  # Will be lazily initialized


# Convenience functions
def optimize_request(request_data: Dict[str, Any], callback: Optional[Callable] = None) -> Dict[str, Any]:
    """Optimize and process request through performance pipeline"""
    return _get_pipeline().optimize_request(request_data, callback)


def get_performance_report() -> Dict[str, Any]:
    """Get current performance report"""
    return _get_pipeline().get_performance_report()


def set_optimization_level(level: str):
    """Set performance optimization level"""
    global _performance_pipeline
    optimization_level = OptimizationLevel(level)
    _performance_pipeline = PerformancePipeline(optimization_level)