import uuid
from decimal import Decimal
from django.test import SimpleTestCase
from apps.procurement.serializers import (GoodsReceiptCreateSerializer)


class GoodsReceiptCreateSerializerTests(SimpleTestCase):

    def setUp(self):
        self.item_id = uuid.uuid4()

        self.valid_payload = {
            "items": [
                {
                    "purchase_order_item_id": str(self.item_id),
                    "quantity_received": "10.000",
                    "quantity_damaged": "1.000",
                }
            ],
            "supplier_reference": "DELIVERY-001",
            "notes": "First delivery",
        }

    def test_valid_payload(self):
        serializer = GoodsReceiptCreateSerializer( data=self.valid_payload )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual( serializer.validated_data["items"][0]["quantity_received"], Decimal("10.000"), )

    def test_damaged_quantity_defaults_to_zero(self):
        payload = {
            "items": [
                {
                    "purchase_order_item_id": str(self.item_id),
                    "quantity_received": "5.000",
                }
            ]
        }

        serializer = GoodsReceiptCreateSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual( serializer.validated_data["items"][0]["quantity_damaged"], Decimal("0.000"), )

    def test_empty_items_rejected(self):
        serializer = GoodsReceiptCreateSerializer( data={"items": []} )
        self.assertFalse(serializer.is_valid())
        self.assertIn("items", serializer.errors)

    def test_zero_received_quantity_rejected(self):
        payload = {
            "items": [
                {
                    "purchase_order_item_id": str(self.item_id),
                    "quantity_received": "0.000",
                }
            ]
        }

        serializer = GoodsReceiptCreateSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_damaged_quantity_cannot_exceed_received(self):
        payload = {
            "items": [
                {
                    "purchase_order_item_id": str(self.item_id),
                    "quantity_received": "5.000",
                    "quantity_damaged": "6.000",
                }
            ]
        }

        serializer = GoodsReceiptCreateSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_duplicate_purchase_order_items_rejected(self):
        payload = {
            "items": [
                {
                    "purchase_order_item_id": str(self.item_id),
                    "quantity_received": "5.000",
                },
                {
                    "purchase_order_item_id": str(self.item_id),
                    "quantity_received": "3.000",
                },
            ]
        }

        serializer = GoodsReceiptCreateSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_invalid_uuid_rejected(self):
        payload = {
            "items": [
                {
                    "purchase_order_item_id": "not-a-uuid",
                    "quantity_received": "5.000",
                }
            ]
        }

        serializer = GoodsReceiptCreateSerializer(data=payload)
        self.assertFalse(serializer.is_valid())