-- Keyword Check - Kobiga: source rows for the APPROVED Product IDs only (automation/scope.json).
-- Parameter %(ids)s = list of approved Product IDs. Read-only. Never run without the ID filter.
-- Returns every row (parent + variation) of each approved listing; fetch_data.py picks the parent row.
select e.item_id, e.id as row_id, e.sku, e.parent_sku, e.title, e.site, e.status, e.is_ended, e.end_date,
       e.is_parent, e.is_child, e.wrong_sku, e.sub_source, s.seller_store_name as account,
       e.product_type as ebay_category_path, e.category_id, e.listing_url, e.selected_variations,
       e.created_at, e.updated_at
from listings.ebay_listings e
left join ebay_campaigns.seller_stores s on s.sub_source = e.sub_source
where e.item_id = any(%(ids)s)
order by e.item_id, e.is_parent desc nulls last, e.id
