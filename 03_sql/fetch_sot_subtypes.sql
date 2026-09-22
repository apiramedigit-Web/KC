-- Keyword Check - Kobiga: SOT Product/Sub-Type for the SKUs of the approved listings only.
-- Parameter %(skus)s = SKUs (parent + variation rows, wrong_sku=0) of the approved Product IDs.
-- Parameter %(keys)s = attribute keys in priority order ('product_subtype', 'sub_type'). Read-only.
select s.sku, a.key, v.value, v.updated_at
from configurator.components_sot_skus s
join configurator.components_sot_attribute_values v on v.sot_sku_id = s.id
join configurator.components_sot_attributes a on a.id = v.attribute_id
where s.sku = any(%(skus)s) and a.key = any(%(keys)s)
order by s.sku, a.key
