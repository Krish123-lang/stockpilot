from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.organizations.models import Organization, Membership
from apps.products.models import Category, Product

from decimal import Decimal
from apps.products.models import ProductVariant

User = get_user_model()


class ProductAPITests(APITestCase):

    def setUp(self):
        self.organization_a = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.organization_b = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        self.user_a = User.objects.create_user(
            email="usera@example.com",
            password="TestPassword123!",
        )

        self.user_b = User.objects.create_user(
            email="userb@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            organization=self.organization_a,
            user=self.user_a,
            role=Membership.Role.OWNER,
        )

        self.category_a = Category.objects.create(
            organization=self.organization_a,
            name="Smartphones",
        )

        self.category_b = Category.objects.create(
            organization=self.organization_b,
            name="Laptops",
        )

        self.product_a = Product.objects.create(
            organization=self.organization_a,
            category=self.category_a,
            name="Samsung Galaxy S25",
        )

        self.product_b = Product.objects.create(
            organization=self.organization_b,
            category=self.category_b,
            name="MacBook Air",
        )

        self.client.force_authenticate(user=self.user_a)

    def test_user_can_list_own_products(self):
        url = reverse(
            "product-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(len(response.data), 1)

        self.assertEqual(
            response.data[0]["name"],
            "Samsung Galaxy S25",
        )

    def test_user_cannot_list_another_organizations_products(self):
        url = reverse(
            "product-list",
            kwargs={
                "organization_id": self.organization_b.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_cannot_retrieve_another_organizations_product(self):
        url = reverse(
            "product-detail",
            kwargs={
                "organization_id": self.organization_a.id,
                "pk": self.product_b.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_product_creation_uses_authenticated_organization(self):
        url = reverse(
            "product-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

        response = self.client.post(
            url,
            {
                "name": "iPhone 17",
                "category": str(self.category_a.id),
                "organization": str(self.organization_b.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        product = Product.objects.get(
            name="iPhone 17",
        )

        self.assertEqual(
            product.organization,
            self.organization_a,
        )

    def test_user_cannot_use_another_organizations_category(self):
        url = reverse(
            "product-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

        response = self.client.post(
            url,
            {
                "name": "Unauthorized Product",
                "category": str(self.category_b.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_user_without_membership_cannot_access_organization(self):
        self.client.force_authenticate(user=self.user_b)

        url = reverse(
            "product-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_can_create_variant_for_own_product(self):
        url = reverse(
            "variant-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

        response = self.client.post(
            url,
            {
                "product": str(self.product_a.id),
                "name": "256 GB",
                "sku": "SAM-S25-256",
                "cost_price": "85000.00",
                "selling_price": "95000.00",
                "unit": "PIECE",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        variant = ProductVariant.objects.get(
            sku="SAM-S25-256",
        )

        self.assertEqual(
            variant.organization,
            self.organization_a,
        )

        self.assertEqual(
            variant.product,
            self.product_a,
        )

    def test_user_cannot_create_variant_for_another_organizations_product(self):
        url = reverse(
            "variant-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

        response = self.client.post(
            url,
            {
                "product": str(self.product_b.id),
                "name": "Base Model",
                "sku": "MACBOOK-AIR",
                "cost_price": "100000.00",
                "selling_price": "120000.00",
                "unit": "PIECE",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
