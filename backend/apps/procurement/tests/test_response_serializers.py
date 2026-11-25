from decimal import Decimal
from django.test import SimpleTestCase
from apps.procurement.serializers import ( GoodsReceiptItemResponseSerializer, GoodsReceiptResponseSerializer)

class GoodsReceiptResponseSerializerTests(SimpleTestCase):

    def test_receipt_item_serializer_exposes_expected_fields(self):
        expected_fields = { "id", "purchase_order_item_id", "quantity_received", "quantity_damaged", "quantity_accepted", "created_at", }
        serializer = GoodsReceiptItemResponseSerializer()
        self.assertEqual(set(serializer.fields.keys()), expected_fields)

    def test_receipt_serializer_exposes_expected_fields(self):
        expected_fields = { "id", "organization_id", "purchase_order_id", "received_by_id", "received_at", "supplier_reference", "notes", "items", "created_at", }
        serializer = GoodsReceiptResponseSerializer()
        self.assertEqual(set(serializer.fields.keys()), expected_fields)

    def test_internal_idempotency_fields_are_not_exposed(self):
        serializer = GoodsReceiptResponseSerializer()
        self.assertNotIn("idempotency_key", serializer.fields)
        self.assertNotIn("request_fingerprint", serializer.fields)

    def test_receipt_fields_are_read_only(self):
        serializer = GoodsReceiptResponseSerializer()

        for field in serializer.fields.values():
            self.assertTrue(field.read_only)

    def test_receipt_item_fields_are_read_only(self):
        serializer = GoodsReceiptItemResponseSerializer()

        for field in serializer.fields.values():
            self.assertTrue(field.read_only)
