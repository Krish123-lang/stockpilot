from django.urls import path
from apps.inventory.views import (InventoryBalanceViewSet,StockMovementViewSet, StockAdjustmentViewSet)

urlpatterns = [
    # Inventory balances
    path("organizations/<uuid:organization_id>/inventory/",InventoryBalanceViewSet.as_view({"get": "list",}),name="inventory-list",),
    path("organizations/<uuid:organization_id>/inventory/<uuid:pk>/",InventoryBalanceViewSet.as_view({"get": "retrieve",}),name="inventory-detail",),
    path("organizations/<uuid:organization_id>/inventory/initialize/",InventoryBalanceViewSet.as_view({"post": "initialize",}),name="inventory-initialize",),
    # Stock movements
    path("organizations/<uuid:organization_id>/stock-movements/",StockMovementViewSet.as_view({"get": "list",}),name="stock-movement-list",),
    path("organizations/<uuid:organization_id>/stock-movements/<uuid:pk>/",StockMovementViewSet.as_view({"get": "retrieve",}),name="stock-movement-detail",),
    # Stock adjustments
    path("organizations/<uuid:organization_id>/stock-adjustments/",StockAdjustmentViewSet.as_view({"get": "list","post": "create",}),name="stock-adjustment-list",),
    path("organizations/<uuid:organization_id>/stock-adjustments/<uuid:pk>/",StockAdjustmentViewSet.as_view({"get": "retrieve",}),name="stock-adjustment-detail",),
    path("organizations/<uuid:organization_id>/stock-adjustments/<uuid:pk>/approve/",StockAdjustmentViewSet.as_view({"post": "approve",}),name="stock-adjustment-approve",),
    path("organizations/<uuid:organization_id>/stock-adjustments/<uuid:pk>/reject/",StockAdjustmentViewSet.as_view({"post": "reject",}),name="stock-adjustment-reject",),
]
