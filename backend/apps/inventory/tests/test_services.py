from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import Organization
from apps.products.models import Product, ProductVariant
from apps.inventory.models import InventoryBalance, StockMovement
from apps.inventory.services import (
    get_or_create_inventory_balance,
    apply_stock_movement,
)


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
