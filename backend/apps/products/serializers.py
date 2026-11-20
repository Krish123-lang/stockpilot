from rest_framework import serializers
from apps.products.models import (Category,Product,ProductVariant)

from django.core.exceptions import ValidationError as DjangoValidationError
from apps.products.services import (
    create_category,
    update_category,
    create_product,
    update_product,
    create_product_variant,
    update_product_variant,
)

class OrganizationScopedSerializer(serializers.ModelSerializer):
    """
    Base serializer that provides the verified organization
    from the authenticated request.
    """

    @property
    def organization(self):
        request = self.context["request"]
        return request.organization_membership.organization
    
    def execute_service(self, service, **kwargs):
        try:
            return service(**kwargs)

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                detail = exc.message_dict
            else:
                detail = exc.messages

            raise serializers.ValidationError(detail)


class CategorySerializer(OrganizationScopedSerializer):

    class Meta:
        model = Category
        fields = ["id","name","description","is_active","created_at","updated_at",]
        read_only_fields = ["id","created_at","updated_at",]
        
    def create(self, validated_data):
        return self.execute_service(
            create_category,
            organization=self.organization,
            **validated_data,
        )


    def update(self, instance, validated_data):
        return self.execute_service(
            update_category,
            instance=instance,
            **validated_data,
        )


class ProductSerializer(OrganizationScopedSerializer):

    class Meta:
        model = Product
        fields = ["id","category","name","description","is_active","created_at","updated_at",]
        read_only_fields = ["id","created_at","updated_at",]

    def get_fields(self):
        fields = super().get_fields()
        fields["category"].queryset = Category.objects.filter(organization=self.organization)
        return fields
    
    def create(self, validated_data):
        return self.execute_service(
            create_product,
            organization=self.organization,
            **validated_data,
        )


    def update(self, instance, validated_data):
        return self.execute_service(
            update_product,
            instance=instance,
            **validated_data,
        )


class ProductVariantSerializer(OrganizationScopedSerializer):

    class Meta:
        model = ProductVariant
        fields = ["id","product","name","sku","barcode","unit","cost_price","selling_price","reorder_level","track_serial_numbers","is_active","created_at","updated_at",]
        read_only_fields = ["id","created_at","updated_at",]

    def get_fields(self):
        fields = super().get_fields()
        fields["product"].queryset = Product.objects.filter(organization=self.organization)
        return fields
    
    def create(self, validated_data):
        return self.execute_service(
            create_product_variant,
            organization=self.organization,
            **validated_data,
        )


    def update(self, instance, validated_data):
        return self.execute_service(
            update_product_variant,
            instance=instance,
            **validated_data,
        )
