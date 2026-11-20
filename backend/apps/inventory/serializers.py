from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from apps.inventory.models import InventoryBalance, StockMovement
from apps.inventory.services import (
    get_or_create_inventory_balance,
    apply_stock_movement,
)
from apps.products.models import ProductVariant


class InventoryBalanceSerializer(serializers.ModelSerializer):
    quantity_sellable = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        read_only=True,
    )

    class Meta:
        model = InventoryBalance
        fields = [
            "id",
            "variant",
            "quantity_on_hand",
            "quantity_damaged",
            "quantity_sellable",
            "updated_at",
        ]

        read_only_fields = fields


class InventoryInitializeSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.none()
    )

    def get_fields(self):
        fields = super().get_fields()

        request = self.context["request"]
        organization = request.organization_membership.organization

        fields["variant"].queryset = ProductVariant.objects.filter(
            organization=organization,
            is_active=True,
        )

        return fields

    def create(self, validated_data):
        request = self.context["request"]
        organization = request.organization_membership.organization

        try:
            return get_or_create_inventory_balance(
                organization=organization,
                variant=validated_data["variant"],
            )

        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

    def to_representation(self, instance):
        return InventoryBalanceSerializer(
            instance,
            context=self.context,
        ).data


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = [
            "id",
            "variant",
            "movement_type",
            "quantity_delta",
            "damaged_delta",
            "quantity_after",
            "damaged_after",
            "reason",
            "created_by",
            "created_at",
        ]

        read_only_fields = fields


class StockMovementCreateSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.none()
    )

    movement_type = serializers.ChoiceField(
        choices=StockMovement.MovementType.choices,
    )

    quantity_delta = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
    )

    damaged_delta = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        required=False,
        default=0,
    )

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def get_fields(self):
        fields = super().get_fields()

        request = self.context["request"]
        organization = request.organization_membership.organization

        fields["variant"].queryset = ProductVariant.objects.filter(
            organization=organization,
            is_active=True,
        )

        return fields

    def create(self, validated_data):
        request = self.context["request"]
        organization = request.organization_membership.organization

        try:
            return apply_stock_movement(
                organization=organization,
                created_by=request.user,
                **validated_data,
            )

        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

    def to_representation(self, instance):
        return StockMovementSerializer(
            instance,
            context=self.context,
        ).data
