"""
Database Adapters Module

Provides adapters for different database types
"""

from .duckdb import DuckDBAdapter, create_sample_database

__all__ = [
    "DuckDBAdapter",
    "create_sample_database",
]
