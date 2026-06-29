"""
Performance Monitoring Utilities

Classes and functions for monitoring system performance:
- PerformanceMonitor class for tracking metrics
- Metric aggregation and reporting
- Timing decorators for operations
- Prometheus metrics export
"""

import asyncio
import functools
import time
import logging
import os
from typing import Dict, List, Callable, Any, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS INTEGRATION
# ============================================================================
METRICS_ENABLED = os.getenv("ENABLE_METRICS", "true").lower() == "true"

# Initialize Prometheus histogram for operation timing (if enabled)
operation_duration_histogram = None
if METRICS_ENABLED:
    try:
        from prometheus_client import Histogram, REGISTRY
        # Try to get existing metric first, create if it doesn't exist
        try:
            operation_duration_histogram = REGISTRY._names_to_collectors.get('operation_duration_seconds')
            if operation_duration_histogram is None:
                operation_duration_histogram = Histogram(
                    'operation_duration_seconds',
                    'Operation duration in seconds',
                    ['operation', 'status'],
                    buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
                )
            logger.info("Prometheus metrics enabled in monitoring utils")
        except ValueError as e:
            # Metric already exists, try to retrieve it
            logger.warning(f"Operation duration metric already exists: {e}")
            operation_duration_histogram = REGISTRY._names_to_collectors.get('operation_duration_seconds')
    except ImportError:
        logger.warning("prometheus_client not installed, metrics disabled")
        METRICS_ENABLED = False


def timed_operation(operation_name: str, log_args: bool = False):
    """
    Decorator to time and log operations with structured logging.

    Supports both sync and async functions.

    Args:
        operation_name: Name of the operation for logging
        log_args: Whether to log function arguments (default: False)

    Usage:
        @timed_operation("llm_call")
        async def call_llm(...):
            ...

        @timed_operation("faiss_retrieve", log_args=True)
        def retrieve(query: str, top_k: int):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()

            # Prepare log extras
            log_extra = {
                "operation": operation_name,
            }

            # Add arguments if requested (useful for debugging)
            if log_args:
                # Convert args to dict (skip 'self' for methods)
                arg_names = func.__code__.co_varnames[:func.__code__.co_argcount]
                if arg_names and arg_names[0] == 'self':
                    arg_dict = dict(zip(arg_names[1:], args[1:]))
                else:
                    arg_dict = dict(zip(arg_names, args))
                log_extra["args"] = {**arg_dict, **kwargs}

            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time
                elapsed_ms = elapsed * 1000

                # Log to structured logs
                logger.info(
                    f"{operation_name} completed",
                    extra={
                        **log_extra,
                        "duration_ms": round(elapsed_ms, 2),
                        "status": "success"
                    }
                )

                # Export to Prometheus (if enabled)
                if METRICS_ENABLED and operation_duration_histogram:
                    operation_duration_histogram.labels(
                        operation=operation_name,
                        status="success"
                    ).observe(elapsed)

                return result

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                elapsed_ms = elapsed * 1000

                # Log error
                logger.error(
                    f"{operation_name} failed",
                    extra={
                        **log_extra,
                        "duration_ms": round(elapsed_ms, 2),
                        "status": "error",
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )

                # Export to Prometheus (if enabled)
                if METRICS_ENABLED and operation_duration_histogram:
                    operation_duration_histogram.labels(
                        operation=operation_name,
                        status="error"
                    ).observe(elapsed)

                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()

            # Prepare log extras
            log_extra = {
                "operation": operation_name,
            }

            # Add arguments if requested
            if log_args:
                arg_names = func.__code__.co_varnames[:func.__code__.co_argcount]
                if arg_names and arg_names[0] == 'self':
                    arg_dict = dict(zip(arg_names[1:], args[1:]))
                else:
                    arg_dict = dict(zip(arg_names, args))
                log_extra["args"] = {**arg_dict, **kwargs}

            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time
                elapsed_ms = elapsed * 1000

                # Log to structured logs
                logger.info(
                    f"{operation_name} completed",
                    extra={
                        **log_extra,
                        "duration_ms": round(elapsed_ms, 2),
                        "status": "success"
                    }
                )

                # Export to Prometheus (if enabled)
                if METRICS_ENABLED and operation_duration_histogram:
                    operation_duration_histogram.labels(
                        operation=operation_name,
                        status="success"
                    ).observe(elapsed)

                return result

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                elapsed_ms = elapsed * 1000

                # Log error
                logger.error(
                    f"{operation_name} failed",
                    extra={
                        **log_extra,
                        "duration_ms": round(elapsed_ms, 2),
                        "status": "error",
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )

                # Export to Prometheus (if enabled)
                if METRICS_ENABLED and operation_duration_histogram:
                    operation_duration_histogram.labels(
                        operation=operation_name,
                        status="error"
                    ).observe(elapsed)

                raise

        # Return async or sync wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class PerformanceMonitor:
    """Monitor and log performance metrics"""

    def __init__(self):
        self.metrics: Dict[str, List[float]] = {
            "retrieval_time": [],
            "generation_time": [],
            "total_time": []
        }

    def log_metric(self, metric_name: str, value: float):
        """Log a performance metric"""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)

        # Keep only last 100 entries per metric
        if len(self.metrics[metric_name]) > 100:
            self.metrics[metric_name] = self.metrics[metric_name][-100:]

    def get_average(self, metric_name: str) -> float:
        """Get average for a metric"""
        values = self.metrics.get(metric_name, [])
        return sum(values) / len(values) if values else 0.0

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all metrics"""
        stats = {}
        for metric_name, values in self.metrics.items():
            if values:
                stats[metric_name] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values)
                }
        return stats

    def print_summary(self):
        """Print performance summary"""
        print("\n[STATS] Performance Summary:")
        for metric_name, values in self.metrics.items():
            if values:
                avg = sum(values) / len(values)
                print(f"  {metric_name}: {avg:.2f}s (avg over {len(values)} calls)")

    def clear_metrics(self):
        """Clear all metrics"""
        for metric_name in self.metrics:
            self.metrics[metric_name] = []
