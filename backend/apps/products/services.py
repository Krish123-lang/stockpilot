from django.core.exceptions import ValidationError
from django.db import transaction

from apps.products.models import (Category, Product, ProductVariant)


@transaction.atomic
def create_category(*, organization, **data):
    category = Category(organization=organization, **data,)
    category.full_clean()
    category.save()
    return category


@transaction.atomic
def update_category(*, instance, **data):
    for field, value in data.items():
        setattr(instance, field, value)

    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def create_product(*, organization, **data):
    product = Product(organization=organization, **data)
    product.full_clean()
    product.save()
    return product


@transaction.atomic
def update_product(*, instance, **data):
    for field, value in data.items():
        setattr(instance, field, value)

    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def create_product_variant(*, organization, **data):
    variant = ProductVariant(organization=organization, **data,)
    variant.full_clean()
    variant.save()
    return variant


@transaction.atomic
def update_product_variant(*, instance, **data):
    for field, value in data.items():
        setattr(instance, field, value)

    instance.full_clean()
    instance.save()
    return instance
