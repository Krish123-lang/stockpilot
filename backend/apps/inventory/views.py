from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.organizations.permissions import IsActiveOrganizationMember
from apps.inventory.models import InventoryBalance, StockMovement
from apps.inventory.serializers import (InventoryBalanceSerializer,InventoryInitializeSerializer,StockMovementSerializer,StockMovementCreateSerializer)


class OrganizationScopedInventoryViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated,IsActiveOrganizationMember,]

    @property
    def organization(self):
        return self.request.organization_membership.organization


class InventoryBalanceViewSet(OrganizationScopedInventoryViewSet):
    queryset = InventoryBalance.objects.all()

    def get_queryset(self):
        return (InventoryBalance.objects.filter(organization=self.organization).select_related("variant", "variant__product").order_by("variant__sku"))

    def get_serializer_class(self):
        if self.action == "initialize":
            return InventoryInitializeSerializer
        return InventoryBalanceSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def initialize(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            balance = serializer.save()

        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)

        response_serializer = InventoryBalanceSerializer(balance,context=self.get_serializer_context(),)
        return Response(response_serializer.data,status=201,)


class StockMovementViewSet(OrganizationScopedInventoryViewSet):
    queryset = StockMovement.objects.all()

    def get_queryset(self):
        return (StockMovement.objects.filter(organization=self.organization).select_related("variant", "variant__product", "created_by").order_by("-created_at"))

    def get_serializer_class(self):
        if self.action == "create":
            return StockMovementCreateSerializer
        return StockMovementSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            movement = serializer.save()

        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)

        response_serializer = StockMovementSerializer(movement,context=self.get_serializer_context(),)
        return Response(response_serializer.data,status=201,)
