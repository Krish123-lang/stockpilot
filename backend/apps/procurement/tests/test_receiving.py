from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.organizations.models import Organization, Membership
from apps.products.models import Product, ProductVariant
from apps.inventory.models import InventoryBalance, StockMovement
from apps.procurement.models import ( Supplier, PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem)
from apps.procurement.services import ( submit_purchase_order, receive_purchase_order)
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.db.models import Sum

User = get_user_model()

class GoodsReceivingServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user( email="receiver@example.com", password="TestPassword123!", )
        self.organization = Organization.objects.create( name="Everest Electronics", slug="everest-electronics", )
        Membership.objects.create( organization=self.organization, user=self.user, role=Membership.Role.INVENTORY, )
        self.supplier = Supplier.objects.create( organization=self.organization, name="ABC Electronics Supplier", )
        self.product = Product.objects.create( organization=self.organization, name="Laptop", )
        self.variant = ProductVariant.objects.create( organization=self.organization, product=self.product, name="Laptop 8GB RAM", sku="LAPTOP-001", unit=ProductVariant.Unit.PIECE, cost_price=Decimal("50000.00"), selling_price=Decimal("60000.00"), )
        self.purchase_order = PurchaseOrder.objects.create( organization=self.organization, supplier=self.supplier, created_by=self.user, )
        self.order_item = PurchaseOrderItem.objects.create( purchase_order=self.purchase_order, variant=self.variant, quantity_ordered=Decimal("10.000"), unit_cost=Decimal("50000.00"),)
        # Submit the PO through the actual business service.
        self.purchase_order = submit_purchase_order( self.purchase_order.id)

    def receive(self, items, **kwargs):
        return receive_purchase_order( purchase_order_id=self.purchase_order.id, received_by=self.user, items=items, **kwargs, )

    def test_first_partial_delivery_updates_inventory_and_status(self):
        receipt = self.receive([{ "purchase_order_item_id": str(self.order_item.id), "quantity_received": "4.000", }])
        self.purchase_order.refresh_from_db()
        balance = InventoryBalance.objects.get( organization=self.organization, variant=self.variant,)
        self.assertIsNotNone(receipt.id)
        self.assertEqual( self.purchase_order.status, PurchaseOrder.Status.PARTIALLY_RECEIVED,)
        self.assertEqual( balance.quantity_on_hand, Decimal("4.000"),)
        self.assertEqual( balance.quantity_damaged, Decimal("0.000"),)
        self.assertEqual(GoodsReceiptItem.objects.filter( goods_receipt=receipt).count(),  1, )

    def test_multiple_deliveries_complete_purchase_order(self):
        self.receive([{ "purchase_order_item_id": str(self.order_item.id), "quantity_received": "4.000", } ])
        second_receipt = self.receive([ { "purchase_order_item_id": str(self.order_item.id), "quantity_received": "6.000", }])
        self.purchase_order.refresh_from_db()
        balance = InventoryBalance.objects.get( organization=self.organization, variant=self.variant, )
        self.assertEqual( self.purchase_order.status, PurchaseOrder.Status.RECEIVED, )
        self.assertEqual( balance.quantity_on_hand, Decimal("10.000"), )
        self.assertEqual( GoodsReceipt.objects.count(), 2, )
        self.assertEqual( second_receipt.items.count(), 1, )

    def test_damaged_goods_are_recorded_separately(self):
        self.receive([ { "purchase_order_item_id": str(self.order_item.id), "quantity_received": "5.000", "quantity_damaged": "2.000", }])
        balance = InventoryBalance.objects.get( organization=self.organization, variant=self.variant,)
        movement = StockMovement.objects.get( organization=self.organization, variant=self.variant, )
        self.assertEqual( balance.quantity_on_hand, Decimal("5.000"), )
        self.assertEqual( balance.quantity_damaged, Decimal("2.000"), )
        self.assertEqual( balance.quantity_sellable, Decimal("3.000"), )
        self.assertEqual( movement.quantity_delta, Decimal("5.000"), )
        self.assertEqual( movement.damaged_delta, Decimal("2.000"), )

    def test_overdelivery_is_rejected_without_changes(self):
        self.receive([
            { "purchase_order_item_id": str(self.order_item.id), "quantity_received": "6.000", } ])

        receipt_count_before = GoodsReceipt.objects.count()
        movement_count_before = StockMovement.objects.count()

        with self.assertRaises(ValidationError):
            self.receive([{ "purchase_order_item_id": str(self.order_item.id), "quantity_received": "5.000", }])

        self.purchase_order.refresh_from_db()
        balance = InventoryBalance.objects.get( organization=self.organization, variant=self.variant, )
        self.assertEqual( self.purchase_order.status, PurchaseOrder.Status.PARTIALLY_RECEIVED, )
        self.assertEqual( balance.quantity_on_hand, Decimal("6.000"), )
        self.assertEqual( GoodsReceipt.objects.count(), receipt_count_before, )
        self.assertEqual( StockMovement.objects.count(), movement_count_before, )

    def test_user_without_membership_cannot_receive_goods(self):
        unauthorized_user = User.objects.create_user( email="unauthorized@example.com", password="TestPassword123!", )

        with self.assertRaises(ValidationError):
            receive_purchase_order( purchase_order_id=self.purchase_order.id, received_by=unauthorized_user, items=[ { "purchase_order_item_id": str(self.order_item.id), "quantity_received": "2.000", } ], )

        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_receipt_item_from_another_purchase_order_is_rejected(self):
        other_organization = Organization.objects.create( name="Himalayan Tech", slug="himalayan-tech", )
        other_supplier = Supplier.objects.create( organization=other_organization, name="Foreign Supplier", )
        other_product = Product.objects.create( organization=other_organization, name="Foreign Laptop", )
        other_variant = ProductVariant.objects.create( organization=other_organization, product=other_product, name="Foreign Laptop Variant", sku="FOREIGN-LAPTOP-001", unit=ProductVariant.Unit.PIECE, cost_price=Decimal("40000.00"), selling_price=Decimal("50000.00"), )
        other_user = User.objects.create_user( email="other@example.com", password="TestPassword123!", )
        other_po = PurchaseOrder.objects.create( organization=other_organization, supplier=other_supplier, created_by=other_user,)
        other_po_item = PurchaseOrderItem.objects.create( purchase_order=other_po, variant=other_variant, quantity_ordered=Decimal("5.000"), unit_cost=Decimal("40000.00"),)
        # The foreign PO must also be submitted.
        submit_purchase_order(other_po.id)

        with self.assertRaises(ValidationError):
            self.receive([ { "purchase_order_item_id": str(other_po_item.id), "quantity_received": "2.000", } ])

        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_failure_during_second_movement_rolls_back_everything(self):
        second_product = Product.objects.create( organization=self.organization, name="Wireless Mouse", )
        second_variant = ProductVariant.objects.create( organization=self.organization, product=second_product, name="Wireless Mouse", sku="MOUSE-001", unit=ProductVariant.Unit.PIECE, cost_price=Decimal("1000.00"), selling_price=Decimal("1500.00"), )
        second_order_item = PurchaseOrderItem.objects.create( purchase_order=self.purchase_order, variant=second_variant, quantity_ordered=Decimal("5.000"), unit_cost=Decimal("1000.00"), )
        
        from apps.procurement import services

        original_apply = services.apply_stock_movement
        call_count = 0

        def fail_on_second_movement(**kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 2:
                raise ValidationError("Simulated inventory failure.")

            return original_apply(**kwargs)

        with patch( "apps.procurement.services.apply_stock_movement", side_effect=fail_on_second_movement,):
            with self.assertRaises(ValidationError):
                self.receive([{ "purchase_order_item_id": str(self.order_item.id), "quantity_received": "3.000",},{ "purchase_order_item_id": str(second_order_item.id), "quantity_received": "2.000",},])

        self.purchase_order.refresh_from_db()
        self.assertEqual(call_count, 2)
        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(GoodsReceiptItem.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(InventoryBalance.objects.count(), 0)

        self.assertEqual( self.purchase_order.status, PurchaseOrder.Status.ORDERED,)

    def test_duplicate_purchase_order_item_is_rejected(self):
        from apps.procurement.models import GoodsReceipt

        items = [
            {"purchase_order_item_id": self.order_item.id,"quantity_received": "2.000","quantity_damaged": "0.000",},
            {"purchase_order_item_id": self.order_item.id,"quantity_received": "1.000","quantity_damaged": "0.000",},
        ]

        with self.assertRaises(ValidationError):
            receive_purchase_order( purchase_order_id=self.purchase_order.id, received_by=self.user, items=items, )

        self.assertEqual( GoodsReceipt.objects.filter( purchase_order=self.purchase_order).count(),0, )
    
    def test_posted_receipt_cannot_be_updated_or_deleted(self):
        from django.db import DatabaseError, transaction

        from apps.procurement.models import GoodsReceipt

        receipt = receive_purchase_order(
            purchase_order_id=self.purchase_order.id,
            received_by=self.user,
            items=[
                { "purchase_order_item_id": self.order_item.id, "quantity_received": "2.000", "quantity_damaged": "0.000", }
            ],
        )

        # The database trigger must reject UPDATE.
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                GoodsReceipt.objects.filter( pk=receipt.pk ).update(notes="Tampered receipt")

        # The database trigger must reject DELETE.
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                GoodsReceipt.objects.filter( pk=receipt.pk ).delete()
                
    def test_posted_receipt_item_cannot_be_updated_or_deleted(self):
        from django.db import DatabaseError, transaction

        from apps.procurement.models import GoodsReceiptItem

        receipt = receive_purchase_order(
            purchase_order_id=self.purchase_order.id,
            received_by=self.user,
            items=[
                { "purchase_order_item_id": self.order_item.id, "quantity_received": "2.000", "quantity_damaged": "0.000", }
            ],
        )
        receipt_item = GoodsReceiptItem.objects.get( goods_receipt=receipt )
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                GoodsReceiptItem.objects.filter( pk=receipt_item.pk ).update(quantity_received="5.000")

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                GoodsReceiptItem.objects.filter( pk=receipt_item.pk ).delete()
                
    def test_same_key_and_same_payload_returns_original_receipt(self):
        items = [
            {
                "purchase_order_item_id": str(self.order_item.id),
                "quantity_received": "2.000",
                "quantity_damaged": "0.000",
            }
        ]

        first_receipt = self.receive(
            items,
            idempotency_key="receipt-request-001",
        )

        second_receipt = self.receive(
            items,
            idempotency_key="receipt-request-001",
        )

        self.assertEqual(first_receipt.id, second_receipt.id)

        self.assertEqual(
            GoodsReceipt.objects.filter(
                organization=self.organization,
                idempotency_key="receipt-request-001",
            ).count(),
            1,
        )

        self.assertEqual(
            StockMovement.objects.filter(
                organization=self.organization,
                variant=self.variant,
            ).count(),
            1,
        )


    def test_same_key_with_different_payload_is_rejected(self):
        self.receive(
            [
                {
                    "purchase_order_item_id": str(self.order_item.id),
                    "quantity_received": "2.000",
                    "quantity_damaged": "0.000",
                }
            ],
            idempotency_key="receipt-request-002",
        )

        with self.assertRaises(ValidationError):
            self.receive(
                [
                    {
                        "purchase_order_item_id": str(self.order_item.id),
                        "quantity_received": "3.000",
                        "quantity_damaged": "0.000",
                    }
                ],
                idempotency_key="receipt-request-002",
            )

        self.assertEqual(GoodsReceipt.objects.count(), 1)

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("2.000"),
        )

        self.assertEqual(StockMovement.objects.count(), 1)


    def test_different_keys_create_separate_receipts(self):
        first_receipt = self.receive(
            [
                {
                    "purchase_order_item_id": str(self.order_item.id),
                    "quantity_received": "2.000",
                }
            ],
            idempotency_key="receipt-request-003",
        )

        second_receipt = self.receive(
            [
                {
                    "purchase_order_item_id": str(self.order_item.id),
                    "quantity_received": "3.000",
                }
            ],
            idempotency_key="receipt-request-004",
        )

        self.assertNotEqual(first_receipt.id, second_receipt.id)
        self.assertEqual(GoodsReceipt.objects.count(), 2)

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("5.000"),
        )


    def test_same_key_can_be_retried_after_po_is_fully_received(self):
        items = [
            {
                "purchase_order_item_id": str(self.order_item.id),
                "quantity_received": "10.000",
                "quantity_damaged": "0.000",
            }
        ]

        first_receipt = self.receive(
            items,
            idempotency_key="receipt-request-005",
        )

        self.purchase_order.refresh_from_db()

        self.assertEqual(
            self.purchase_order.status,
            PurchaseOrder.Status.RECEIVED,
        )

        second_receipt = self.receive(
            items,
            idempotency_key="receipt-request-005",
        )

        self.assertEqual(first_receipt.id, second_receipt.id)
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

@skipUnless(connection.vendor == "postgresql", "This concurrency test requires PostgreSQL row-level locking.")
class GoodsReceivingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(
            email="concurrent-receiver@example.com",
            password="TestPassword123!",
        )

        self.organization = Organization.objects.create(
            name="Concurrency Electronics",
            slug="concurrency-electronics",
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.INVENTORY,
        )

        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Concurrency Supplier",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Concurrency Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="Concurrency Laptop Variant",
            sku="CONCURRENT-LAPTOP-001",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
        )

        self.purchase_order = PurchaseOrder.objects.create(
            organization=self.organization,
            supplier=self.supplier,
            created_by=self.user,
        )

        self.order_item = PurchaseOrderItem.objects.create(
            purchase_order=self.purchase_order,
            variant=self.variant,
            quantity_ordered=Decimal("10.000"),
            unit_cost=Decimal("50000.00"),
        )

        self.purchase_order = submit_purchase_order(
            self.purchase_order.id
        )

    def test_concurrent_receipts_cannot_overdeliver(self):
        barrier = Barrier(2)

        def receive_six_units():
            close_old_connections()

            try:
                barrier.wait(timeout=10)

                receipt = receive_purchase_order(
                    purchase_order_id=self.purchase_order.id,
                    received_by=self.user,
                    items=[
                        {
                            "purchase_order_item_id": str(
                                self.order_item.id
                            ),
                            "quantity_received": "6.000",
                            "quantity_damaged": "0.000",
                        }
                    ],
                )

                return ("received", str(receipt.id))

            except ValidationError:
                return ("rejected", None)

            finally:
                # close_old_connections()
                from django.db import connections
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(receive_six_units),
                executor.submit(receive_six_units),
            ]

            results = [future.result(timeout=30) for future in futures]

        # Close any remaining connections in the test-runner thread.
        from django.db import connections
        connections.close_all()

        statuses = [result[0] for result in results]

        self.assertEqual(statuses.count("received"), 1)
        self.assertEqual(statuses.count("rejected"), 1)

        # Only one receipt should have been committed.
        self.assertEqual(
            GoodsReceipt.objects.filter(
                purchase_order=self.purchase_order
            ).count(),
            1,
        )

        total_received = GoodsReceiptItem.objects.filter(
            purchase_order_item=self.order_item
        ).aggregate(total=Sum("quantity_received"))["total"]

        self.assertEqual(total_received, Decimal("6.000"))

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("6.000"),
        )

        self.purchase_order.refresh_from_db()

        self.assertEqual(
            self.purchase_order.status,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
        )


    def test_concurrent_identical_requests_create_one_receipt(self):
        barrier = Barrier(2)

        def receive_same_request():
            close_old_connections()

            try:
                barrier.wait(timeout=10)

                receipt = receive_purchase_order(
                    purchase_order_id=self.purchase_order.id,
                    received_by=self.user,
                    items=[
                        {
                            "purchase_order_item_id": str(
                                self.order_item.id
                            ),
                            "quantity_received": "6.000",
                        }
                    ],
                    idempotency_key="concurrent-receipt-001",
                )

                return receipt.pk

            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(receive_same_request)
                for _ in range(2)
            ]

            receipt_ids = [
                future.result(timeout=30)
                for future in futures
            ]

        self.assertEqual(receipt_ids[0], receipt_ids[1])

        self.assertEqual(
            GoodsReceipt.objects.filter(
                organization=self.organization,
                idempotency_key="concurrent-receipt-001",
            ).count(),
            1,
        )

        self.assertEqual(
            GoodsReceiptItem.objects.filter(
                goods_receipt__id=receipt_ids[0]
            ).count(),
            1,
        )

        self.assertEqual(
            StockMovement.objects.filter(
                variant=self.order_item.variant
            ).count(),
            1,
        )
