from django.urls import path
from apps.procurement.views import GoodsReceiptViewSet, PurchaseOrderViewSet

urlpatterns = [
    path("organizations/<uuid:organization_id>/purchase-orders/", PurchaseOrderViewSet.as_view({"get": "list"}), name="purchase-order-list",),
    path("organizations/<uuid:organization_id>/purchase-orders/<uuid:pk>/", PurchaseOrderViewSet.as_view({"get": "retrieve"}), name="purchase-order-detail",),
    path("organizations/<uuid:organization_id>/purchase-orders/<uuid:purchase_order_id>/receipts/", GoodsReceiptViewSet.as_view({"post": "create"}), name="goods-receipt-create", ),
]
