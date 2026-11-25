from django.urls import path
from apps.procurement.views import GoodsReceiptViewSet

urlpatterns = [
    path("organizations/<uuid:organization_id>/purchase-orders/<uuid:purchase_order_id>/receipts/", GoodsReceiptViewSet.as_view({"post": "create"}), name="goods-receipt-create", ),
]
