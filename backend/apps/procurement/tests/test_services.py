from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, close_old_connections
from django.test import TransactionTestCase

from apps.inventory.models import InventoryBalance, StockMovement
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import Organization
from apps.products.models import Product, ProductVariant
from apps.procurement.models import (PurchaseOrder,PurchaseOrderItem,PurchaseOrderSequence,Supplier)
from apps.procurement.services import submit_purchase_order


User = get_user_model()


class PurchaseOrderSubmissionTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="test-password",
        )

        self.org_a = Organization.objects.create(
            name="Organization A",
            slug="organization-a",
        )

        self.org_b = Organization.objects.create(
            name="Organization B",
            slug="organization-b",
        )

        self.supplier_a = Supplier.objects.create(
            organization=self.org_a,
            name="Supplier A",
        )

        self.product_a = Product.objects.create(
            organization=self.org_a,
            name="Product A",
        )

        self.variant_a = ProductVariant.objects.create(
            organization=self.org_a,
            product=self.product_a,
            name="Variant A",
            sku="VAR-A",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

    def create_purchase_order(self, organization=None, supplier=None):
        organization = organization or self.org_a
        supplier = supplier or self.supplier_a

        return PurchaseOrder.objects.create(
            organization=organization,
            supplier=supplier,
            created_by=self.user,
        )

    def add_item(self, purchase_order):
        return PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            variant=self.variant_a,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("100.00"),
        )

    def test_successful_submission(self):
        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        submitted = submit_purchase_order(purchase_order.id)

        submitted.refresh_from_db()

        self.assertEqual(
            submitted.status,
            PurchaseOrder.Status.ORDERED,
        )
        self.assertIsNotNone(submitted.order_number)
        self.assertEqual(
            submitted.submitted_at,
            submitted.ordered_at,
        )

    def test_order_number_has_expected_format(self):
        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        submitted = submit_purchase_order(purchase_order.id)

        expected_prefix = f"PO-{timezone.localdate().year}-"

        self.assertTrue(
            submitted.order_number.startswith(expected_prefix)
        )
        self.assertEqual(
            len(submitted.order_number),
            len(expected_prefix) + 6,
        )

    def test_sequence_increments_within_organization(self):
        first = self.create_purchase_order()
        second = self.create_purchase_order()

        self.add_item(first)
        self.add_item(second)

        first = submit_purchase_order(first.id)
        second = submit_purchase_order(second.id)

        self.assertTrue(first.order_number.endswith("000001"))
        self.assertTrue(second.order_number.endswith("000002"))

    def test_each_organization_has_independent_sequence(self):
        supplier_b = Supplier.objects.create(
            organization=self.org_b,
            name="Supplier B",
        )

        product_b = Product.objects.create(
            organization=self.org_b,
            name="Product B",
        )

        variant_b = ProductVariant.objects.create(
            organization=self.org_b,
            product=product_b,
            name="Variant B",
            sku="VAR-B",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        po_a = self.create_purchase_order()

        po_b = self.create_purchase_order(
            organization=self.org_b,
            supplier=supplier_b,
        )

        self.add_item(po_a)

        PurchaseOrderItem.objects.create(
            purchase_order=po_b,
            variant=variant_b,
            quantity_ordered=Decimal("1.000"),
            unit_cost=Decimal("100.00"),
        )

        submitted_a = submit_purchase_order(po_a.id)
        submitted_b = submit_purchase_order(po_b.id)

        self.assertTrue(submitted_a.order_number.endswith("000001"))
        self.assertTrue(submitted_b.order_number.endswith("000001"))

    def test_empty_purchase_order_cannot_be_submitted(self):
        purchase_order = self.create_purchase_order()

        with self.assertRaises(ValidationError):
            submit_purchase_order(purchase_order.id)

        purchase_order.refresh_from_db()

        self.assertEqual(
            purchase_order.status,
            PurchaseOrder.Status.DRAFT,
        )
        self.assertIsNone(purchase_order.order_number)

    def test_inactive_supplier_cannot_receive_new_order(self):
        self.supplier_a.is_active = False
        self.supplier_a.save(update_fields=["is_active"])

        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        with self.assertRaises(ValidationError):
            submit_purchase_order(purchase_order.id)

        purchase_order.refresh_from_db()

        self.assertEqual(
            purchase_order.status,
            PurchaseOrder.Status.DRAFT,
        )
        self.assertIsNone(purchase_order.order_number)

    def test_submitted_purchase_order_cannot_be_submitted_again(self):
        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        first_submission = submit_purchase_order(purchase_order.id)

        with self.assertRaises(ValidationError):
            submit_purchase_order(purchase_order.id)

        purchase_order.refresh_from_db()

        self.assertEqual(
            purchase_order.order_number,
            first_submission.order_number,
        )

    
    def test_failed_submission_rolls_back_sequence_increment(self):
        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        with patch.object(
            PurchaseOrder,
            "save",
            side_effect=RuntimeError("Simulated database failure"),
        ):
            with self.assertRaises(RuntimeError):
                submit_purchase_order(purchase_order.id)

        purchase_order.refresh_from_db()

        self.assertFalse(
            PurchaseOrderSequence.objects.filter(
                organization=self.org_a,
                year=timezone.localdate().year,
            ).exists()
        )

        self.assertEqual(
            purchase_order.status,
            PurchaseOrder.Status.DRAFT,
        )
        self.assertIsNone(purchase_order.order_number)
    
    
    def test_failed_submission_preserves_existing_sequence_number(self):
        current_year = timezone.localdate().year

        sequence = PurchaseOrderSequence.objects.create(
            organization=self.org_a,
            year=current_year,
            last_number=7,
        )

        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        with patch.object(
            PurchaseOrder,
            "save",
            side_effect=RuntimeError("Simulated database failure"),
        ):
            with self.assertRaises(RuntimeError):
                submit_purchase_order(purchase_order.id)

        sequence.refresh_from_db()

        self.assertEqual(sequence.last_number, 7)

        purchase_order.refresh_from_db()

        self.assertEqual(
            purchase_order.status,
            PurchaseOrder.Status.DRAFT,
        )
        self.assertIsNone(purchase_order.order_number)
        
    
    def test_submission_does_not_change_inventory_or_create_movements(self):
        balance = InventoryBalance.objects.create(
            organization=self.org_a,
            variant=self.variant_a,
            quantity_on_hand=Decimal("12.000"),
            quantity_damaged=Decimal("2.000"),
        )

        initial_movement_count = StockMovement.objects.filter(
            organization=self.org_a,
            variant=self.variant_a,
        ).count()

        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        submit_purchase_order(purchase_order.id)

        balance.refresh_from_db()

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("12.000"),
        )
        self.assertEqual(
            balance.quantity_damaged,
            Decimal("2.000"),
        )

        final_movement_count = StockMovement.objects.filter(
            organization=self.org_a,
            variant=self.variant_a,
        ).count()

        self.assertEqual(
            final_movement_count,
            initial_movement_count,
        )


    def test_submission_does_not_create_inventory_balance(self):
        self.assertFalse(
            InventoryBalance.objects.filter(
                organization=self.org_a,
                variant=self.variant_a,
            ).exists()
        )

        purchase_order = self.create_purchase_order()
        self.add_item(purchase_order)

        submit_purchase_order(purchase_order.id)

        self.assertFalse(
            InventoryBalance.objects.filter(
                organization=self.org_a,
                variant=self.variant_a,
            ).exists()
        )

class PurchaseOrderConcurrencyTests(TransactionTestCase):

    reset_sequences = True

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="concurrency@example.com",
            password="test-password",
        )

        self.org = Organization.objects.create(
            name="Concurrency Organization",
            slug="concurrency-org",
        )

        self.supplier = Supplier.objects.create(
            organization=self.org,
            name="Concurrency Supplier",
            is_active=True,
        )

        self.product = Product.objects.create(
            organization=self.org,
            name="Concurrency Product",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.org,
            product=self.product,
            name="Standard",
            sku="CONCURRENCY-001",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        # Create the sequence first so this test focuses on
        # concurrent increments rather than concurrent creation.
        PurchaseOrderSequence.objects.create(
            organization=self.org,
            year=timezone.localdate().year,
            last_number=0,
        )

    def create_order(self):
        purchase_order = PurchaseOrder.objects.create(
            organization=self.org,
            supplier=self.supplier,
            created_by=self.user,
        )

        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            variant=self.variant,
            quantity_ordered=Decimal("5.000"),
            unit_cost=Decimal("100.00"),
        )

        return purchase_order

    def test_concurrent_submissions_receive_unique_numbers(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "This concurrency test requires PostgreSQL row locking."
            )

        first_order = self.create_order()
        second_order = self.create_order()

        barrier = Barrier(2)

        def submit_order(order_id):
            close_old_connections()

            try:
                barrier.wait(timeout=10)

                submitted = submit_purchase_order(order_id)
                return submitted.order_number

            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(
                submit_order,
                first_order.id,
            )
            second_future = executor.submit(
                submit_order,
                second_order.id,
            )

            order_numbers = [
                first_future.result(timeout=30),
                second_future.result(timeout=30),
            ]

        self.assertEqual(len(set(order_numbers)), 2)

        expected_numbers = {
            f"PO-{timezone.localdate().year}-000001",
            f"PO-{timezone.localdate().year}-000002",
        }

        self.assertEqual(set(order_numbers), expected_numbers)