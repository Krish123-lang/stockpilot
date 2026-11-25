from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.procurement.models import (GoodsReceipt,GoodsReceiptItem, PurchaseOrder,PurchaseOrderItem,PurchaseOrderSequence,Supplier)
from decimal import Decimal
from django.db.models import Sum
from apps.inventory.models import StockMovement
from apps.inventory.services import (apply_stock_movement,get_or_create_inventory_balance,validate_inventory_quantity)
from apps.organizations.models import Membership
import hashlib
import json
from django.db import IntegrityError

@transaction.atomic
def submit_purchase_order(purchase_order_id):
    """
    Submit a draft purchase order.

    Responsibilities:
    - Lock the purchase order.
    - Validate the supplier and purchase order items.
    - Generate a unique organization-specific order number.
    - Transition the PO from DRAFT to ORDERED.
    - Roll back everything if any operation fails.
    """

    # Lock the purchase order to prevent concurrent submissions.
    try:
        purchase_order = (PurchaseOrder.objects.select_for_update().get(pk=purchase_order_id))
    except PurchaseOrder.DoesNotExist:
        raise ValidationError("Purchase order does not exist.")

    # Only drafts can be submitted.
    if purchase_order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("Only draft purchase orders can be submitted.")

    if purchase_order.order_number is not None:
        raise ValidationError("This purchase order already has an order number.")

    # Lock the supplier so its active state cannot change
    # concurrently while this submission is being processed.
    try:
        supplier = (Supplier.objects.select_for_update().get(pk=purchase_order.supplier_id))
    except Supplier.DoesNotExist:
        raise ValidationError("Purchase order supplier does not exist.")

    if not supplier.is_active:
        raise ValidationError("Cannot submit a purchase order to an inactive supplier.")

    if supplier.organization_id != purchase_order.organization_id:
        raise ValidationError("Supplier must belong to the purchase order organization.")

    # Lock and load the purchase order items.
    items = list(PurchaseOrderItem.objects.select_for_update().select_related("variant").filter(purchase_order=purchase_order))

    if not items:
        raise ValidationError("A purchase order must contain at least one item.")

    # Validate the purchase order and every item.
    purchase_order.full_clean()

    for item in items:
        item.full_clean()

    # Use the configured local timezone.
    now = timezone.now()
    year = timezone.localdate().year

    # get_or_create handles the race when two transactions
    # attempt to create the same organization/year sequence.
    sequence, _ = PurchaseOrderSequence.objects.get_or_create(organization_id=purchase_order.organization_id,year=year,defaults={"last_number": 0},)

    # Lock the sequence row before incrementing it.
    sequence = (PurchaseOrderSequence.objects.select_for_update().get(pk=sequence.pk))
    sequence.last_number += 1
    sequence.save(update_fields=["last_number", "updated_at"])

    # Generate the organization-specific purchase order number.
    order_number = f"PO-{year}-{sequence.last_number:06d}"

    # Update the purchase order.
    purchase_order.order_number = order_number
    purchase_order.status = PurchaseOrder.Status.ORDERED
    purchase_order.submitted_at = now
    purchase_order.ordered_at = now

    purchase_order.full_clean()

    purchase_order.save(update_fields=["order_number","status","submitted_at","ordered_at","updated_at",])
    return purchase_order

def build_receipt_fingerprint( *, purchase_order_id, normalized_items, supplier_reference, notes, received_at):
    """
    Create a deterministic SHA-256 fingerprint for a receipt request.

    Equivalent Decimal values such as 2 and 2.000 produce
    the same canonical quantity representation.
    """

    canonical_items = []

    for line in normalized_items:
        canonical_items.append({
            "purchase_order_item_id": str( line["order_item"].id),
            "quantity_received": format(line["quantity_received"].normalize(), "f",),
            "quantity_damaged": format( line["quantity_damaged"].normalize(), "f",),
        })

    canonical_items.sort( key=lambda item: item["purchase_order_item_id"])

    payload = {
        "purchase_order_id": str(purchase_order_id),
        "items": canonical_items,
        "supplier_reference": (supplier_reference or "").strip(),
        "notes": (notes or "").strip(),
        "received_at": (
            received_at.isoformat()
            if received_at is not None
            else None
        ),
    }

    serialized = json.dumps(payload,sort_keys=True,separators=(",", ":"),)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

@transaction.atomic
def receive_purchase_order(*,purchase_order_id,received_by,items,supplier_reference="",notes="",received_at=None,  idempotency_key=None,):
    """
    Record a physical delivery against an ordered purchase order.

    Each item must contain:
        purchase_order_item_id
        quantity_received
        quantity_damaged (optional; defaults to zero)

    Receipt creation, inventory movements, and PO status updates
    are committed or rolled back together.
    """

    # 1. Lock the purchase order.
    try:
        purchase_order = (PurchaseOrder.objects.select_for_update().select_related("organization", "supplier").get(id=purchase_order_id))
    except PurchaseOrder.DoesNotExist:
        raise ValidationError("Purchase order does not exist.")

    organization = purchase_order.organization

    # 2. Validate organization and receiving user.
    if not organization.is_active:
        raise ValidationError("This organization is inactive.")

    if not received_by.is_active:
        raise ValidationError("This user account is inactive.")

    membership = Membership.objects.filter(
        organization=organization,
        user=received_by,
        is_active=True,
        organization__is_active=True,
        role__in=[Membership.Role.OWNER,Membership.Role.MANAGER,Membership.Role.INVENTORY,],).first()

    if membership is None:
        raise ValidationError("You are not authorized to receive goods for this organization.")
    
    if idempotency_key is not None:
        if not isinstance(idempotency_key, str):
            raise ValidationError("Idempotency key must be a string.")

        idempotency_key = idempotency_key.strip()

        if not idempotency_key:
            raise ValidationError("Idempotency key cannot be empty.")

        if len(idempotency_key) > 128:
            raise ValidationError("Idempotency key cannot exceed 128 characters.")

    # 4. Validate the submitted receipt lines.
    if not isinstance(items, list) or not items:
        raise ValidationError("A goods receipt must contain at least one item.")

    # Lock all PO items in a consistent order.
    purchase_order_items = list(PurchaseOrderItem.objects.select_for_update().select_related("variant").filter(purchase_order=purchase_order).order_by("id"))

    if not purchase_order_items:
        raise ValidationError("This purchase order has no items.")

    order_items_by_id = { str(item.id): item for item in purchase_order_items }

    normalized_items = []
    seen_item_ids = set()

    for submitted_item in items:
        if not isinstance(submitted_item, dict):
            raise ValidationError("Each receipt item must be an object.")

        item_id = submitted_item.get("purchase_order_item_id")

        if not item_id:
            raise ValidationError("Every receipt item must specify a purchase-order item ID.")

        item_id = str(item_id)

        if item_id in seen_item_ids:
            raise ValidationError("A purchase-order item cannot appear twice in one receipt.")

        seen_item_ids.add(item_id)
        order_item = order_items_by_id.get(item_id)

        if order_item is None:
            raise ValidationError("A receipt item does not belong to this purchase order.")

        quantity_received = validate_inventory_quantity(submitted_item.get("quantity_received"),field_name="quantity_received",)

        quantity_damaged = validate_inventory_quantity(submitted_item.get("quantity_damaged", Decimal("0.000")),field_name="quantity_damaged",)

        if quantity_received <= 0:
            raise ValidationError("Received quantity must be greater than zero.")

        if quantity_damaged < 0 or quantity_damaged > quantity_received:
            raise ValidationError("Damaged quantity must be between zero and received quantity.")

        normalized_items.append({"order_item": order_item,"quantity_received": quantity_received,"quantity_damaged": quantity_damaged,})
    normalized_items.sort(key=lambda line: str(line["order_item"].variant_id))
    
    request_fingerprint = None

    if idempotency_key is not None:
        request_fingerprint = build_receipt_fingerprint(
            purchase_order_id=purchase_order.id,
            normalized_items=normalized_items,
            supplier_reference=supplier_reference,
            notes=notes,
            received_at=received_at,
        )

        existing_receipt = GoodsReceipt.objects.filter(
            organization=organization,
            idempotency_key=idempotency_key,
        ).first()

        if existing_receipt is not None:
            if existing_receipt.request_fingerprint != request_fingerprint:
                raise ValidationError(
                    "This idempotency key has already been used "
                    "with a different receipt request."
                )

            return existing_receipt


    # Check status ONLY after the idempotency lookup.
    if purchase_order.status not in [
        PurchaseOrder.Status.ORDERED,
        PurchaseOrder.Status.PARTIALLY_RECEIVED,
    ]:
        raise ValidationError(
            "Only ordered or partially received purchase orders "
            "can receive goods."
        )

    # 5. Check cumulative quantities before creating any receipt records.
    incoming_by_item = { str(line["order_item"].id): line["quantity_received"] for line in normalized_items}

    received_totals = {}

    for order_item in purchase_order_items:
        previous_total = (GoodsReceiptItem.objects.filter(purchase_order_item=order_item).aggregate(total=Sum("quantity_received"))["total"] or Decimal("0.000"))

        incoming = incoming_by_item.get( str(order_item.id), Decimal("0.000"),)
        cumulative_total = previous_total + incoming

        if cumulative_total > order_item.quantity_ordered:
            remaining = order_item.quantity_ordered - previous_total

            raise ValidationError(
                f"Overdelivery detected for SKU {order_item.variant.sku}. "
                f"Remaining quantity: {remaining}."
            )
        received_totals[str(order_item.id)] = cumulative_total

    # 6. Create the immutable receipt header.
    receipt = GoodsReceipt(
        organization=organization,
        purchase_order=purchase_order,
        received_by=received_by,
        received_at=received_at or timezone.now(),
        supplier_reference=(supplier_reference or "").strip(),
        notes=(notes or "").strip(),
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )

    # Validate model fields and clean(), while leaving the database
    # unique constraint to handle concurrent requests safely.
    receipt.full_clean(validate_constraints=False)

    try:
        # The inner atomic block creates a savepoint. If the unique
        # constraint fails, the outer transaction remains usable.
        with transaction.atomic():
            receipt.save()

    except IntegrityError:
        if idempotency_key is None:
            raise

        existing_receipt = GoodsReceipt.objects.filter(
            organization=organization,
            idempotency_key=idempotency_key,
        ).first()

        if existing_receipt is None:
            raise

        if existing_receipt.request_fingerprint != request_fingerprint:
            raise ValidationError(
                "This idempotency key has already been used "
                "with a different receipt request."
            )

        return existing_receipt

    # 7. Create receipt lines and update inventory.
    for line in normalized_items:
        order_item = line["order_item"]
        quantity_received = line["quantity_received"]
        quantity_damaged = line["quantity_damaged"]
        receipt_item = GoodsReceiptItem( goods_receipt=receipt, purchase_order_item=order_item, quantity_received=quantity_received, quantity_damaged=quantity_damaged,)
        receipt_item.full_clean()
        receipt_item.save()

        # The inventory service requires an existing balance.
        get_or_create_inventory_balance( organization=organization, variant=order_item.variant,)
        apply_stock_movement( organization=organization, variant=order_item.variant, movement_type=StockMovement.MovementType.RECEIPT, quantity_delta=quantity_received, damaged_delta=quantity_damaged, created_by=received_by, reason=f"Goods receipt {receipt.id}",)

    # 8. Recalculate purchase-order status.
    fully_received = all( received_totals[str(order_item.id)] >= order_item.quantity_ordered for order_item in purchase_order_items)
    purchase_order.status = ( PurchaseOrder.Status.RECEIVED if fully_received else PurchaseOrder.Status.PARTIALLY_RECEIVED)
    purchase_order.save(update_fields=["status", "updated_at"])
    return receipt