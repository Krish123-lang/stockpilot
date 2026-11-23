
from django.db import migrations


FORWARD_SQL = """
-- Validate the supplier and existing items whenever a purchase order
-- is inserted or its organization/supplier is changed.
CREATE OR REPLACE FUNCTION procurement_validate_purchase_order_tenant()
RETURNS TRIGGER AS $$
DECLARE
    supplier_org UUID;
BEGIN
    SELECT organization_id
    INTO supplier_org
    FROM procurement_supplier
    WHERE id = NEW.supplier_id;

    IF supplier_org IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION
            'Purchase order and supplier must belong to the same organization.'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM procurement_purchaseorderitem poi
        JOIN products_productvariant pv ON pv.id = poi.variant_id
        WHERE poi.purchase_order_id = NEW.id
        AND pv.organization_id IS DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION
            'Purchase order and its product variants must belong to the same organization.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER procurement_purchase_order_tenant_check
BEFORE INSERT OR UPDATE OF organization_id, supplier_id
ON procurement_purchaseorder
FOR EACH ROW
EXECUTE FUNCTION procurement_validate_purchase_order_tenant();


-- Prevent changing a supplier's organization if that would invalidate
-- an existing purchase order.
CREATE OR REPLACE FUNCTION procurement_validate_supplier_tenant_update()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM procurement_purchaseorder po
        WHERE po.supplier_id = NEW.id
        AND po.organization_id IS DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION
            'Cannot change supplier organization while linked purchase orders exist.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER procurement_supplier_tenant_update_check
BEFORE UPDATE OF organization_id
ON procurement_supplier
FOR EACH ROW
EXECUTE FUNCTION procurement_validate_supplier_tenant_update();


-- Validate every purchase order item against its purchase order.
CREATE OR REPLACE FUNCTION procurement_validate_purchase_order_item_tenant()
RETURNS TRIGGER AS $$
DECLARE
    purchase_order_org UUID;
    variant_org UUID;
BEGIN
    SELECT organization_id
    INTO purchase_order_org
    FROM procurement_purchaseorder
    WHERE id = NEW.purchase_order_id;

    SELECT organization_id
    INTO variant_org
    FROM products_productvariant
    WHERE id = NEW.variant_id;

    IF purchase_order_org IS DISTINCT FROM variant_org THEN
        RAISE EXCEPTION
            'Purchase order and product variant must belong to the same organization.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER procurement_purchase_order_item_tenant_check
BEFORE INSERT OR UPDATE OF purchase_order_id, variant_id
ON procurement_purchaseorderitem
FOR EACH ROW
EXECUTE FUNCTION procurement_validate_purchase_order_item_tenant();


-- Prevent changing a variant's organization if existing purchase order
-- items would become cross-tenant.
CREATE OR REPLACE FUNCTION procurement_validate_variant_tenant_update()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM procurement_purchaseorderitem poi
        JOIN procurement_purchaseorder po
            ON po.id = poi.purchase_order_id
        WHERE poi.variant_id = NEW.id
        AND po.organization_id IS DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION
            'Cannot change product variant organization while linked purchase order items exist.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER procurement_variant_tenant_update_check
BEFORE UPDATE OF organization_id
ON products_productvariant
FOR EACH ROW
EXECUTE FUNCTION procurement_validate_variant_tenant_update();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS procurement_variant_tenant_update_check
ON products_productvariant;
DROP FUNCTION IF EXISTS procurement_validate_variant_tenant_update();

DROP TRIGGER IF EXISTS procurement_purchase_order_item_tenant_check
ON procurement_purchaseorderitem;
DROP FUNCTION IF EXISTS procurement_validate_purchase_order_item_tenant();

DROP TRIGGER IF EXISTS procurement_supplier_tenant_update_check
ON procurement_supplier;
DROP FUNCTION IF EXISTS procurement_validate_supplier_tenant_update();

DROP TRIGGER IF EXISTS procurement_purchase_order_tenant_check
ON procurement_purchaseorder;
DROP FUNCTION IF EXISTS procurement_validate_purchase_order_tenant();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("procurement", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
