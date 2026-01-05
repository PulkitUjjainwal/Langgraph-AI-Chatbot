"""
Performance Monitoring Utilities

Classes and functions for monitoring system performance:
- PerformanceMonitor class for tracking metrics
- Metric aggregation and reporting
"""

from typing import Dict, List


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
