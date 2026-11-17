
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate
from rest_framework.views import APIView

from apps.organizations.models import Organization, Membership
from apps.organizations.permissions import IsActiveOrganizationMember


User = get_user_model()


class OrganizationProbeView(APIView):
    permission_classes = [IsActiveOrganizationMember]

    def get(self, request, organization_id):
        return Response({
            "organization_id": str(
                request.organization_membership.organization_id
            )
        })


class OrganizationPermissionTests(APITestCase):

    def setUp(self):
        self.factory = APIRequestFactory()

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

    def make_request(self, user, organization_id):
        request = self.factory.get(
            f"/api/v1/organizations/{organization_id}/probe/"
        )

        force_authenticate(request, user=user)

        view = OrganizationProbeView.as_view()

        return view(
            request,
            organization_id=str(organization_id),
        )

    def test_active_member_can_access_organization(self):
        response = self.make_request(
            self.user_a,
            self.organization_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_member_cannot_access_another_organization(self):
        response = self.make_request(
            self.user_a,
            self.organization_b.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_non_member_cannot_access_organization(self):
        response = self.make_request(
            self.user_b,
            self.organization_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_inactive_membership_cannot_access_organization(self):
        membership = Membership.objects.get(
            user=self.user_a,
            organization=self.organization_a,
        )

        membership.is_active = False
        membership.save(update_fields=["is_active"])

        response = self.make_request(
            self.user_a,
            self.organization_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_inactive_organization_cannot_be_accessed(self):
        self.organization_a.is_active = False
        self.organization_a.save(update_fields=["is_active"])

        response = self.make_request(
            self.user_a,
            self.organization_a.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
