from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Membership, Organization

User = get_user_model()


class OrganizationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="krishna@example.com",
            password="Test-Only-Password-123!",
        )

        self.organization = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

    def test_user_can_join_multiple_organizations(self):
        second_organization = Organization.objects.create(
            name="TechMart",
            slug="techmart",
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.OWNER
        )

        Membership.objects.create(
            organization=second_organization,
            user=self.user,
            role=Membership.Role.MANAGER
        )
        self.assertEqual(self.user.memberships.count(), 2)

    def test_duplicate_membership_is_rejected(self):
        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    organization=self.organization,
                    user=self.user,
                    role=Membership.Role.MANAGER
                )

    def test_membership_has_correct_role(self):
        membership = Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.SALES
        )
        self.assertEqual(
            membership.role,
            membership.Role.SALES
        )
