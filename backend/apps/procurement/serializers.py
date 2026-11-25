from decimal import Decimal
from rest_framework import serializers
from apps.procurement.models import GoodsReceipt, GoodsReceiptItem
from apps.procurement.models import ( Supplier, PurchaseOrder, PurchaseOrderItem,)

class GoodsReceiptItemInputSerializer(serializers.Serializer):
    purchase_order_item_id = serializers.UUIDField()
    quantity_received = serializers.DecimalField( max_digits=14, decimal_places=3, min_value=Decimal("0.001"), )
    quantity_damaged = serializers.DecimalField( max_digits=14, decimal_places=3, required=False, default=Decimal("0.000"), min_value=Decimal("0.000"), )

    def validate(self, attrs):
        quantity_received = attrs["quantity_received"]
        quantity_damaged = attrs["quantity_damaged"]

        if quantity_damaged > quantity_received:
            raise serializers.ValidationError({ "quantity_damaged": ( "Damaged quantity cannot exceed received quantity." ) })

        return attrs

class GoodsReceiptCreateSerializer(serializers.Serializer):
    items = GoodsReceiptItemInputSerializer( many=True, allow_empty=False, )
    supplier_reference = serializers.CharField( max_length=100, required=False, allow_blank=True, default="", )
    notes = serializers.CharField( required=False, allow_blank=True, default="", )
    
    def validate_items(self, items):
        item_ids = [ item["purchase_order_item_id"] for item in items ]

        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError( "A purchase-order item cannot appear twice in one receipt." )
        return items


class GoodsReceiptItemResponseSerializer(serializers.ModelSerializer):
    purchase_order_item_id = serializers.UUIDField(read_only=True)
    quantity_accepted = serializers.DecimalField( max_digits=14, decimal_places=3, read_only=True,)

    class Meta:
        model = GoodsReceiptItem
        fields = [ "id", "purchase_order_item_id", "quantity_received", "quantity_damaged", "quantity_accepted", "created_at", ]
        read_only_fields = fields


class GoodsReceiptResponseSerializer(serializers.ModelSerializer):
    items = GoodsReceiptItemResponseSerializer(many=True, read_only=True)
    purchase_order_id = serializers.UUIDField(read_only=True)
    organization_id = serializers.UUIDField(read_only=True)
    received_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = [ "id", "organization_id", "purchase_order_id", "received_by_id", "received_at", "supplier_reference", "notes", "items", "created_at", ]
        read_only_fields = fields


class PurchaseOrderSupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name"]
        read_only_fields = fields


class PurchaseOrderItemResponseSerializer(serializers.ModelSerializer):
    variant_id = serializers.UUIDField(read_only=True)
    sku = serializers.CharField( source="variant.sku", read_only=True,)
    variant_name = serializers.CharField( source="variant.name", read_only=True,)
    product_name = serializers.CharField( source="variant.product.name", read_only=True,)
    unit = serializers.CharField( source="variant.unit", read_only=True, )
    line_total = serializers.DecimalField( max_digits=16, decimal_places=2, read_only=True, )

    class Meta:
        model = PurchaseOrderItem
        fields = [ "id", "variant_id", "product_name", "variant_name", "sku", "unit", "quantity_ordered", "unit_cost", "line_total", "created_at", ]
        read_only_fields = fields


class PurchaseOrderListSerializer(serializers.ModelSerializer):
    supplier = PurchaseOrderSupplierSerializer(read_only=True)
    total_amount = serializers.DecimalField( max_digits=16, decimal_places=2, read_only=True,)
    created_by_email = serializers.EmailField( source="created_by.email", read_only=True, )

    class Meta:
        model = PurchaseOrder
        fields = [ "id", "order_number", "supplier", "status", "total_amount", "expected_delivery_date", "created_by_email", "created_at",]
        read_only_fields = fields


class PurchaseOrderDetailSerializer(PurchaseOrderListSerializer):
    items = PurchaseOrderItemResponseSerializer( many=True, read_only=True,)

    class Meta(PurchaseOrderListSerializer.Meta):
        fields = [ *PurchaseOrderListSerializer.Meta.fields, "ordered_at", "submitted_at", "notes", "items", "updated_at",]
        read_only_fields = fields
