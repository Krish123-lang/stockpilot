from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
# from django.test import TransactionTestCase
from django.db import IntegrityError, transaction, connection
from apps.organizations.models import Organization
from apps.products.models import Product, ProductVariant
from apps.inventory.models import InventoryBalance, StockAdjustment, StockMovement
from apps.inventory.services import (get_or_create_inventory_balance, apply_stock_movement, validate_inventory_quantity)
from django.test import TestCase

User = get_user_model()


class InventoryServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
        )

        self.organization = Organization.objects.create(
            name="Test Electronics",
            slug="test-electronics",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="Laptop 8GB RAM",
            sku="LAPTOP-001",
            unit="PIECE",
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
            reorder_level=Decimal("2.000"),
        )

    def initialize_inventory(self):
        return get_or_create_inventory_balance(
            organization=self.organization,
            variant=self.variant,
        )

    def test_initialize_inventory_balance(self):
        balance = self.initialize_inventory()

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("0.000"),
        )

        self.assertEqual(
            balance.quantity_damaged,
            Decimal("0.000"),
        )

        self.assertEqual(
            balance.quantity_sellable,
            Decimal("0.000"),
        )

    def test_reject_variant_from_another_organization(self):
        another_organization = Organization.objects.create(
            name="Another Electronics",
            slug="another-electronics",
        )

        with self.assertRaises(ValidationError):
            get_or_create_inventory_balance(
                organization=another_organization,
                variant=self.variant,
            )

    def test_receive_stock(self):
        self.initialize_inventory()

        movement = apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            created_by=self.user,
            reason="Initial stock receipt",
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("10.000"),
        )

        self.assertEqual(
            balance.quantity_sellable,
            Decimal("10.000"),
        )

        self.assertEqual(
            movement.quantity_after,
            Decimal("10.000"),
        )

    def test_sell_stock(self):
        self.initialize_inventory()

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            created_by=self.user,
        )

        movement = apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.SALE,
            quantity_delta=Decimal("-3.000"),
            created_by=self.user,
            reason="Customer purchase",
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("7.000"),
        )

        self.assertEqual(
            balance.quantity_sellable,
            Decimal("7.000"),
        )

        self.assertEqual(
            movement.quantity_after,
            Decimal("7.000"),
        )

    def test_reject_sale_causing_negative_stock(self):
        self.initialize_inventory()

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.SALE,
                quantity_delta=Decimal("-11.000"),
                created_by=self.user,
            )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("10.000"),
        )

    def test_record_damaged_customer_return(self):
        self.initialize_inventory()

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            created_by=self.user,
        )

        movement = apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.CUSTOMER_RETURN,
            quantity_delta=Decimal("1.000"),
            damaged_delta=Decimal("1.000"),
            created_by=self.user,
            reason="Customer returned damaged laptop",
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("11.000"),
        )

        self.assertEqual(
            balance.quantity_damaged,
            Decimal("1.000"),
        )

        self.assertEqual(
            balance.quantity_sellable,
            Decimal("10.000"),
        )

        self.assertEqual(
            movement.damaged_after,
            Decimal("1.000"),
        )

    def test_repair_damaged_inventory(self):
        self.initialize_inventory()

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            created_by=self.user,
        )

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.CUSTOMER_RETURN,
            quantity_delta=Decimal("1.000"),
            damaged_delta=Decimal("1.000"),
            created_by=self.user,
        )

        movement = apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.REPAIR,
            quantity_delta=Decimal("0.000"),
            damaged_delta=Decimal("-1.000"),
            created_by=self.user,
            reason="Laptop repaired",
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("11.000"),
        )

        self.assertEqual(
            balance.quantity_damaged,
            Decimal("0.000"),
        )

        self.assertEqual(
            balance.quantity_sellable,
            Decimal("11.000"),
        )

        self.assertEqual(
            movement.damaged_after,
            Decimal("0.000"),
        )

    def test_reject_invalid_movement_type(self):
        self.initialize_inventory()

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type="INVALID_MOVEMENT",
                quantity_delta=Decimal("5.000"),
                created_by=self.user,
            )

    def test_failed_movement_does_not_change_balance(self):
        self.initialize_inventory()

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("5.000"),
            created_by=self.user,
        )

        movement_count_before = StockMovement.objects.count()

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.SALE,
                quantity_delta=Decimal("-8.000"),
                created_by=self.user,
            )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("5.000"),
        )

        self.assertEqual(
            balance.quantity_damaged,
            Decimal("0.000"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            movement_count_before,
        )

    def test_sale_cannot_increase_inventory(self):
        self.initialize_inventory()

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.SALE,
                quantity_delta=Decimal("5.000"),
                created_by=self.user,
            )

    def test_damage_movement_changes_only_damaged_quantity(self):
        self.initialize_inventory()

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("5.000"),
            created_by=self.user,
        )

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.DAMAGE,
            quantity_delta=Decimal("0.000"),
            damaged_delta=Decimal("1.000"),
            created_by=self.user,
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(balance.quantity_on_hand, Decimal("5.000"))
        self.assertEqual(balance.quantity_damaged, Decimal("1.000"))
        self.assertEqual(balance.quantity_sellable, Decimal("4.000"))

    def test_damage_movement_cannot_change_physical_quantity(self):
        self.initialize_inventory()

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.DAMAGE,
                quantity_delta=Decimal("-1.000"),
                damaged_delta=Decimal("1.000"),
                created_by=self.user,
            )

    def test_repair_must_reduce_damaged_quantity(self):
        self.initialize_inventory()

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.REPAIR,
                quantity_delta=Decimal("0.000"),
                damaged_delta=Decimal("1.000"),
                created_by=self.user,
            )

    def test_reversal_requires_dedicated_logic(self):
        self.initialize_inventory()

        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.REVERSAL,
                quantity_delta=Decimal("1.000"),
                created_by=self.user,
            )

    def test_receipt_with_zero_damaged_quantity_succeeds(self):
        InventoryBalance.objects.create(
            organization=self.organization, variant=self.variant,)
        movement = apply_stock_movement(organization=self.organization, variant=self.variant, movement_type=StockMovement.MovementType.RECEIPT, quantity_delta=Decimal(
            "10.000"), damaged_delta=Decimal("0.000"), created_by=self.user, reason="Normal goods receipt",)
        balance = InventoryBalance.objects.get(
            organization=self.organization, variant=self.variant,)
        self.assertEqual(balance.quantity_on_hand, Decimal("10.000"),)
        self.assertEqual(balance.quantity_damaged, Decimal("0.000"),)
        self.assertEqual(movement.quantity_delta, Decimal("10.000"),)

    def test_receipt_with_valid_damaged_quantity_succeeds(self):
        InventoryBalance.objects.create(
            organization=self.organization, variant=self.variant,)
        movement = apply_stock_movement(organization=self.organization, variant=self.variant, movement_type=StockMovement.MovementType.RECEIPT, quantity_delta=Decimal(
            "10.000"), damaged_delta=Decimal("2.000"), created_by=self.user, reason="Receipt containing damaged goods",)
        balance = InventoryBalance.objects.get(
            organization=self.organization, variant=self.variant,)
        self.assertEqual(balance.quantity_on_hand, Decimal("10.000"),)
        self.assertEqual(balance.quantity_damaged, Decimal("2.000"),)
        self.assertEqual(balance.quantity_sellable, Decimal("8.000"),)

    def test_receipt_with_negative_damaged_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity_delta=Decimal("10.000"),
                damaged_delta=Decimal("-1.000"),
                created_by=self.user,
                reason="Invalid receipt",
            )

        self.assertFalse(
            StockMovement.objects.filter(
                organization=self.organization,
                variant=self.variant,
            ).exists()
        )

    def test_receipt_with_damaged_quantity_above_received_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            apply_stock_movement(
                organization=self.organization,
                variant=self.variant,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity_delta=Decimal("10.000"),
                damaged_delta=Decimal("11.000"),
                created_by=self.user,
                reason="Invalid receipt",
            )

        self.assertFalse(
            StockMovement.objects.filter(
                organization=self.organization,
                variant=self.variant,
            ).exists()
        )

    def test_quantity_validator_accepts_three_decimal_places(self):
        result = validate_inventory_quantity("12.345")

        self.assertEqual(result, Decimal("12.345"))

    def test_quantity_validator_accepts_trailing_zeroes(self):
        result = validate_inventory_quantity("12.3400")

        self.assertEqual(result, Decimal("12.3400"))

    def test_quantity_validator_rejects_more_than_three_decimal_places(self):
        with self.assertRaises(ValidationError):
            validate_inventory_quantity("12.3456")

    def test_quantity_validator_rejects_more_than_eleven_integer_digits(self):
        with self.assertRaises(ValidationError):
            validate_inventory_quantity("100000000000.000")

    def test_quantity_validator_rejects_nan(self):
        with self.assertRaises(ValidationError):
            validate_inventory_quantity("NaN")

    def test_quantity_validator_rejects_infinity(self):
        with self.assertRaises(ValidationError):
            validate_inventory_quantity("Infinity")

    def test_quantity_validator_rejects_invalid_text(self):
        with self.assertRaises(ValidationError):
            validate_inventory_quantity("not-a-number")

    def create_test_movement(self):
        InventoryBalance.objects.get_or_create(
            organization=self.organization,
            variant=self.variant,
        )

        return apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            damaged_delta=Decimal("0.000"),
            created_by=self.user,
            reason="Test receipt",
        )

    def test_existing_stock_movement_cannot_be_updated(self):
        movement = self.create_test_movement()

        movement.reason = "Modified reason"

        with self.assertRaises(ValidationError):
            movement.save()

        movement.refresh_from_db()

        self.assertEqual(movement.reason, "Test receipt")

    def test_existing_stock_movement_cannot_be_deleted(self):
        movement = self.create_test_movement()
        movement_id = movement.id

        with self.assertRaises(ValidationError):
            movement.delete()

        self.assertTrue(
            StockMovement.objects.filter(id=movement_id).exists()
        )

    def test_stock_movement_queryset_update_is_blocked(self):
        movement = self.create_test_movement()

        with self.assertRaises(ValidationError):
            StockMovement.objects.filter(
                id=movement.id
            ).update(reason="Modified reason")

        movement.refresh_from_db()

        self.assertEqual(movement.reason, "Test receipt")

    def test_stock_movement_queryset_delete_is_blocked(self):
        movement = self.create_test_movement()

        with self.assertRaises(ValidationError):
            StockMovement.objects.filter(
                id=movement.id
            ).delete()

        self.assertTrue(
            StockMovement.objects.filter(id=movement.id).exists()
        )

    def test_stock_movement_bulk_create_is_blocked(self):
        movement = self.create_test_movement()

        new_movement = StockMovement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("5.000"),
            damaged_delta=Decimal("0.000"),
            quantity_after=Decimal("15.000"),
            damaged_after=Decimal("0.000"),
            created_by=self.user,
            reason="Attempted bulk creation",
        )

        with self.assertRaises(ValidationError):
            StockMovement.objects.bulk_create([new_movement])

        self.assertEqual(StockMovement.objects.count(), 1)

    def test_database_rejects_inventory_balance_for_foreign_variant(self):
        other_organization = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        other_product = Product.objects.create(
            organization=other_organization,
            name="Foreign Product",
        )

        foreign_variant = ProductVariant.objects.create(
            organization=other_organization,
            product=other_product,
            name="Foreign Variant",
            sku="FOREIGN-001",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryBalance.objects.create(
                    organization=self.organization,
                    variant=foreign_variant,
                )

    def test_database_rejects_stock_movement_for_foreign_variant(self):
        other_organization = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        other_product = Product.objects.create(
            organization=other_organization,
            name="Foreign Product",
        )

        foreign_variant = ProductVariant.objects.create(
            organization=other_organization,
            product=other_product,
            name="Foreign Variant",
            sku="FOREIGN-002",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(
                    organization=self.organization,
                    variant=foreign_variant,
                    movement_type=StockMovement.MovementType.RECEIPT,
                    quantity_delta=Decimal("5.000"),
                    damaged_delta=Decimal("0.000"),
                    quantity_after=Decimal("5.000"),
                    damaged_after=Decimal("0.000"),
                    created_by=self.user,
                    reason="Invalid tenant test",
                )

    def test_database_rejects_stock_adjustment_for_foreign_variant(self):
        other_organization = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        other_product = Product.objects.create(
            organization=other_organization,
            name="Foreign Product",
        )

        foreign_variant = ProductVariant.objects.create(
            organization=other_organization,
            product=other_product,
            name="Foreign Variant",
            sku="FOREIGN-003",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockAdjustment.objects.create(
                    organization=self.organization,
                    variant=foreign_variant,
                    quantity_change=Decimal("5.000"),
                    damaged_quantity_change=Decimal("0.000"),
                    reason="Invalid tenant test",
                    created_by=self.user,
                )

    def test_database_rejects_variant_with_foreign_product_organization(self):
        foreign_org = Organization.objects.create(
            name="Foreign Organization",
            slug="foreign-organization",
        )

        foreign_product = Product.objects.create(
            organization=foreign_org,
            name="Foreign Product",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.filter(
                    pk=self.variant.pk
                ).update(product=foreign_product)

    def test_database_rejects_variant_organization_mismatch(self):
        foreign_org = Organization.objects.create(
            name="Foreign Organization",
            slug="foreign-organization",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.filter(
                    pk=self.variant.pk
                ).update(organization=foreign_org)

    def test_database_prevents_product_organization_change_with_variants(self):
        foreign_org = Organization.objects.create(
            name="Foreign Organization",
            slug="foreign-organization",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.filter(
                    pk=self.variant.product_id
                ).update(organization=foreign_org)

    def test_database_prevents_stock_movement_update(self):
        # Reuse the movement creation setup from your existing
        # stock movement immutability test.
        movement = self.create_test_movement()  # Create a valid StockMovement using your service.

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE inventory_stockmovement
                        SET reason = %s
                        WHERE id = %s
                        """,
                        ["Tampered reason", movement.pk],
                    )

    def test_database_prevents_stock_movement_delete(self):
        # Reuse the movement creation setup from your existing
        # stock movement immutability test.
        movement = self.create_test_movement()  # Create a valid StockMovement using your service.

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM inventory_stockmovement
                        WHERE id = %s
                        """,
                        [movement.pk],
                    )

    def test_database_prevents_variant_ownership_change_with_inventory_records(self):
        # Create an inventory balance for the existing variant.
        self.initialize_inventory()

        foreign_org = Organization.objects.create(
            name="Foreign Organization",
            slug="foreign-organization",
        )

        foreign_product = Product.objects.create(
            organization=foreign_org,
            name="Foreign Product",
        )

        # Changing BOTH fields must still be rejected.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.filter(
                    pk=self.variant.pk
                ).update(
                    organization=foreign_org,
                    product=foreign_product,
                )

        # Verify the original ownership remains unchanged.
        self.variant.refresh_from_db()

        self.assertEqual(self.variant.organization_id, self.organization.id)
        self.assertEqual(self.variant.product_id, self.product.id)

#     def test_database_prevents_stock_movement_truncate(self):
#         self.create_test_movement()

#         movement_count_before = StockMovement.objects.count()
#         self.assertEqual(movement_count_before, 1)

#         with self.assertRaises(IntegrityError):
#             with transaction.atomic():
#                 with connection.cursor() as cursor:
#                     cursor.execute(
#                         "TRUNCATE TABLE inventory_stockmovement"
#                     )

#         self.assertEqual(
#             StockMovement.objects.count(),
#             movement_count_before,
#         )

# class StockMovementDatabaseIntegrityTests(TransactionTestCase):
#     reset_sequences = True

#     def test_database_prevents_stock_movement_truncate(self):
#         # Recreate the required organization, user,
#         # product, variant, and stock movement here.

#         movement = self.create_test_movement()

#         with self.assertRaises(IntegrityError):
#             with connection.cursor() as cursor:
#                 cursor.execute(
#                     "TRUNCATE TABLE inventory_stockmovement"
#                 )

#         self.assertTrue(
#             StockMovement.objects.filter(pk=movement.pk).exists()
#         )