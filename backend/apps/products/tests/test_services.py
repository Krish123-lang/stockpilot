
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import Organization
from apps.products.models import Category, Product
from apps.products.services import (
    create_product,
    create_product_variant,
)


class ProductServiceTests(TestCase):

    def setUp(self):
        self.organization_a = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.organization_b = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        self.category_a = Category.objects.create(
            organization=self.organization_a,
            name="Smartphones",
        )

        self.category_b = Category.objects.create(
            organization=self.organization_b,
            name="Laptops",
        )

    def test_create_product_for_organization(self):
        product = create_product(
            organization=self.organization_a,
            name="Samsung Galaxy S25",
            category=self.category_a,
        )

        self.assertEqual(
            product.organization,
            self.organization_a,
        )

    def test_reject_category_from_another_organization(self):
        with self.assertRaises(ValidationError):
            create_product(
                organization=self.organization_a,
                name="Unauthorized Product",
                category=self.category_b,
            )

        self.assertFalse(
            Product.objects.filter(
                name="Unauthorized Product"
            ).exists()
        )

    def test_create_product_variant(self):
        product = create_product(
            organization=self.organization_a,
            name="Samsung Galaxy S25",
            category=self.category_a,
        )

        variant = create_product_variant(
            organization=self.organization_a,
            product=product,
            name="256 GB",
            sku="SAM-S25-256",
            cost_price=Decimal("85000.00"),
            selling_price=Decimal("95000.00"),
        )

        self.assertEqual(variant.product, product)
        self.assertEqual(variant.organization, self.organization_a)

    def test_reject_product_from_another_organization(self):
        product = create_product(
            organization=self.organization_b,
            name="MacBook Air",
            category=self.category_b,
        )

        with self.assertRaises(ValidationError):
            create_product_variant(
                organization=self.organization_a,
                product=product,
                name="Default",
                sku="MACBOOK-AIR",
                cost_price=Decimal("100000.00"),
                selling_price=Decimal("120000.00"),
            )

    def test_reject_negative_variant_price(self):
        product = create_product(
            organization=self.organization_a,
            name="Samsung Galaxy S25",
            category=self.category_a,
        )

        with self.assertRaises(ValidationError):
            create_product_variant(
                organization=self.organization_a,
                product=product,
                name="Invalid Variant",
                sku="INVALID-PRICE",
                cost_price=Decimal("-100.00"),
                selling_price=Decimal("95000.00"),
            )
