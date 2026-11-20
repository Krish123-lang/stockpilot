from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Organization
from apps.products.models import Category, Product, ProductVariant

User = get_user_model()

class ProductModelTests(TestCase):

    def setUp(self):
        self.organization_a = Organization.objects.create(name="Everest Electronics",slug="everest-electronics",)
        self.organization_b = Organization.objects.create(name="Himalayan Tech",slug="himalayan-tech",)
        self.category = Category.objects.create(organization=self.organization_a,name="Smartphones",)
        self.product = Product.objects.create(organization=self.organization_a,category=self.category,name="Samsung Galaxy S25",)

    def create_variant(self, sku="SAM-S25-256"):
        return ProductVariant.objects.create(organization=self.organization_a,product=self.product,name="256 GB",sku=sku,cost_price=Decimal("85000.00"),selling_price=Decimal("95000.00"),)

    def test_product_belongs_to_organization(self):
        self.assertEqual(self.product.organization,self.organization_a,)

    def test_variant_has_decimal_prices(self):
        variant = self.create_variant()
        self.assertEqual(variant.cost_price,Decimal("85000.00"),)
        self.assertEqual(variant.selling_price,Decimal("95000.00"),)

    def test_same_sku_allowed_in_different_organizations(self):
        self.create_variant()
        other_product = Product.objects.create(organization=self.organization_b,name="Samsung Galaxy S25",)
        variant = ProductVariant.objects.create(organization=self.organization_b,product=other_product,sku="SAM-S25-256",cost_price=Decimal("85000.00"),selling_price=Decimal("95000.00"),)
        self.assertEqual(variant.organization,self.organization_b,)

    def test_duplicate_sku_rejected_within_organization(self):
        self.create_variant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_variant(sku="sam-s25-256")

    def test_negative_cost_price_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(organization=self.organization_a,product=self.product,sku="INVALID-COST",cost_price=Decimal("-1.00"),selling_price=Decimal("100.00"),)

    def test_category_name_is_case_insensitive_unique_per_org(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(organization=self.organization_a,name="smartphones",)
