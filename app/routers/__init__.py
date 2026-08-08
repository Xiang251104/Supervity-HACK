# app/routers/__init__.py
"""
API Routers - Modular endpoint organization.

Note: File endpoints are defined in main.py to maintain proper path ordering.
"""

from .admin import router as admin_router
from .ap_data_manager import router as ap_data_manager_router
from .ap_insights import router as ap_insights_router
from .ap_metrics import router as ap_metrics_router
from .ap_policies import router as ap_policies_router
from .ap_runs import router as ap_runs_router
from .ap_workbench import router as ap_workbench_router
from .audit import router as audit_router
from .auth import router as auth_router
from .examples import router as examples_router
from .health import router as health_router
from .items import router as items_router

__all__ = [
    "health_router",
    "auth_router",
    "admin_router",
    "ap_data_manager_router",
    "ap_insights_router",
    "ap_metrics_router",
    "ap_policies_router",
    "ap_runs_router",
    "ap_workbench_router",
    "audit_router",
    "items_router",
    "examples_router",
]
