from django.urls import path

from apps.inventory.views import (
    InventoryBalanceViewSet,
    StockMovementViewSet,
)


urlpatterns = [
    # Inventory balances
    path(
        "organizations/<uuid:organization_id>/inventory/",
        InventoryBalanceViewSet.as_view({
            "get": "list",
        }),
        name="inventory-list",
    ),

    path(
        "organizations/<uuid:organization_id>/inventory/<uuid:pk>/",
        InventoryBalanceViewSet.as_view({
            "get": "retrieve",
        }),
        name="inventory-detail",
    ),

    path(
        "organizations/<uuid:organization_id>/inventory/initialize/",
        InventoryBalanceViewSet.as_view({
            "post": "initialize",
        }),
        name="inventory-initialize",
    ),

    # Stock movements
    path(
        "organizations/<uuid:organization_id>/stock-movements/",
        StockMovementViewSet.as_view({
            "get": "list",
            "post": "create",
        }),
        name="stock-movement-list",
    ),

    path(
        "organizations/<uuid:organization_id>/stock-movements/<uuid:pk>/",
        StockMovementViewSet.as_view({
            "get": "retrieve",
        }),
        name="stock-movement-detail",
    ),
]
