from django.urls import path
from . import views, dashboard_views

urlpatterns = [
    # ── Public API (inventory page) ───────────────────────────────────────────
    path('inventory/', views.inventory_list, name='inventory-list'),
    path('borrow/',    views.submit_borrow,  name='submit-borrow'),

    # ── Dashboard API ─────────────────────────────────────────────────────────
    # Reference data
    path('dashboard/item-types/', dashboard_views.dashboard_item_types,  name='dash-item-types'),
    path('dashboard/locations/',  dashboard_views.dashboard_locations,    name='dash-locations'),

    # Items CRUD
    path('dashboard/items/',             dashboard_views.dashboard_items,       name='dash-items'),
    path('dashboard/items/<int:item_id>/', dashboard_views.dashboard_item_detail, name='dash-item-detail'),

    # Borrow requests
    path('dashboard/requests/',             dashboard_views.dashboard_requests,       name='dash-requests'),
    path('dashboard/requests/<int:req_id>/', dashboard_views.dashboard_request_detail, name='dash-request-detail'),

    # Schedule / timeline
    path('dashboard/schedule/', dashboard_views.dashboard_schedule, name='dash-schedule'),

    # Diagnostics / IT status
    path('dashboard/diagnostics/', dashboard_views.dashboard_diagnostics, name='dash-diagnostics'),
]

