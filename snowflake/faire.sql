WITH faire_orders AS (
    SELECT
        "id"::varchar AS order_id,
        "company_name" AS customer_name
    FROM dwh.prod.fact_shopify_orders
    WHERE "source_name" ILIKE '%faire%'
    GROUP BY ALL
),

gross_rev_by_faire_customer AS (    
    SELECT
        CONVERT_TIMEZONE('UTC', COALESCE(ao."brand_timezone", 'America/New_York'), ao."purchase_date_utc")::date AS date,
        ao."brand" AS brand,
        customer_name,
        order_id,
        "sku" AS sku,
        "product_name" AS item_name,
        SUM(COALESCE(ao."gross_revenue_lc", 0)) AS gross_rev,
        SUM(COALESCE(-ao."item_promotion_discount_lc", 0)) AS discounts,
        SUM(COALESCE(ao."shipping_price_per_unit" * ao."quantity", 0)) AS shipping,
        SUM(COALESCE(ao."quantity", 0)) AS units_ordered
    FROM dwh.prod.fact_all_orders AS ao
    INNER JOIN faire_orders AS f
        ON ao."external_order_id" = f.order_id
    WHERE CONVERT_TIMEZONE('UTC', COALESCE(ao."brand_timezone", 'America/New_York'), ao."purchase_date_utc")::date >= '2024-01-01'
    GROUP BY ALL
),

returns_sku_union AS (
    SELECT
        r."marketplace",
        r."country_code",
        r."external_order_id",
        r."sku",
        r."brand",
        CONVERT_TIMEZONE('UTC', COALESCE(ao."brand_timezone", 'America/New_York'), "refund_date_utc")::date AS "day",
        SUM(COALESCE(ao."gross_revenue_lc", 0)) AS sku_gross_rev,
        r."quantity" AS units_returned
    FROM dwh.prod.fact_all_refunds_v2 AS r
    LEFT JOIN dwh.prod.fact_all_orders AS ao
        ON r."brand" = ao."brand"
            AND r."external_order_id" = ao."external_order_id"
            AND r."marketplace" = ao."marketplace"
            AND r."country_code" = ao."country_code"
            AND r."sku" = ao."sku"
    WHERE r."marketplace" = 'SHOPIFY'
        AND r."country_code" = 'US'
        AND CONVERT_TIMEZONE('UTC',COALESCE(ao."brand_timezone", 'America/New_York'), "refund_date_utc")::date >= '2024-01-01'
        AND r."quantity" <> 0
        AND r."sku" IS NOT NULL
    GROUP BY ALL
    
    UNION ALL
    
    SELECT
        r."marketplace",
        r."country_code",
        r."external_order_id",
        ao."sku",
        r."brand",
        CONVERT_TIMEZONE('UTC', COALESCE(ao."brand_timezone", 'America/New_York'), "refund_date_utc")::date AS "day",
        SUM(COALESCE("gross_revenue_lc", 0)) AS sku_gross_rev,
        ao."quantity" AS units_returned
    FROM dwh.prod.fact_all_refunds_v2 AS r
    LEFT JOIN dwh.prod.fact_all_orders AS ao
        ON r."brand" = ao."brand"
            AND r."external_order_id" = ao."external_order_id"
            AND r."marketplace" = ao."marketplace"
            AND r."country_code" = ao."country_code"
    WHERE CONVERT_TIMEZONE('UTC', COALESCE(ao."brand_timezone", 'America/New_York'), "refund_date_utc")::date >= '2024-01-01'
        AND r."marketplace" = 'SHOPIFY'
        AND r."country_code" = 'US'
        AND r."sku" IS NULL
        AND r."quantity" <> 0
        AND ao."sku" IS NOT NULL
    GROUP BY ALL
),

returns_sku AS (
    SELECT
        "marketplace",
        "country_code",
        "external_order_id",
        "sku",
        "brand",
        "day",
        SUM(COALESCE(sku_gross_rev, 0)) AS sku_gross_rev,
        SUM(COALESCE(units_returned, 0)) AS units_returned
    FROM returns_sku_union
    GROUP BY ALL
),

unique_order AS (
    SELECT DISTINCT
        "brand",
        "external_order_id",
        "marketplace",
        "country_code",
        "brand_timezone"
    FROM dwh.prod.fact_all_orders
),

brand_r AS (
    SELECT
        r."marketplace",
        r."country_code",
        r."brand",
        CONVERT_TIMEZONE('UTC', COALESCE(uo."brand_timezone", 'America/New_York'), "refund_date_utc")::date AS "day",
        r."external_order_id",
        SUM(COALESCE("product_refund", 0))
            + SUM(CASE WHEN r."quantity" > 0 THEN 0 ELSE COALESCE("other_refund", 0) END + CASE WHEN r."quantity" > 0 AND COALESCE("product_refund", 0) = 0 THEN COALESCE("other_refund", 0) ELSE 0 END) AS returns,
    FROM dwh.prod.fact_all_refunds_v2 AS r
    LEFT JOIN unique_order AS uo
        ON r."brand" = uo."brand"
            AND r."external_order_id" = uo."external_order_id"
            AND r."marketplace" = uo."marketplace"
            AND r."country_code" = uo."country_code"
    WHERE r."marketplace" = 'SHOPIFY'
        AND r."country_code" = 'US'
        AND CONVERT_TIMEZONE('UTC', COALESCE(uo."brand_timezone", 'America/New_York'), "refund_date_utc")::date >= '2024-01-01'
    GROUP BY ALL
),

returns_by_order AS (
    SELECT DISTINCT
        rs."brand" AS brand,
        rs."sku" AS sku,
        rs."day" AS date,
        rs."external_order_id",
        DIV0(
            SUM(COALESCE(rs.sku_gross_rev, 0)) OVER (PARTITION BY 
                rs."marketplace",
                rs."country_code",
                rs."brand",
                rs."sku",
                rs."day",
                rs."external_order_id"),
            SUM(COALESCE(rs.sku_gross_rev, 0)) OVER (PARTITION BY 
                rs."marketplace",
                rs."country_code",
                rs."brand",
                rs."day",
                rs."external_order_id")
        ) * COALESCE(br.returns, 0) AS returns,
        rs.units_returned
    FROM returns_sku AS rs
    LEFT JOIN brand_r AS br
        ON rs."marketplace" = br."marketplace"
            AND rs."country_code" = br."country_code"
            AND rs."external_order_id" = br."external_order_id"
            AND rs."brand" = br."brand"
            AND rs."day" = br."day"
),

returns_by_faire_customer AS (
    SELECT
        r.date,
        r.brand,
        customer_name,
        sku,
        SUM(COALESCE(r.returns, 0)) AS returns,
        CASE
            WHEN SUM(COALESCE(r.returns, 0)) = 0 THEN 0
            ELSE SUM(COALESCE(r.units_returned, 0)) 
        END AS units_returned,
    FROM returns_by_order AS r
    INNER JOIN faire_orders AS f
        ON r."external_order_id" = f.order_id
    GROUP BY ALL
),

item_name_mapping AS (
    SELECT
        date AS latest_sku_date,
        sku,
        netsuite_item_number,
        item_name
    FROM gross_rev_by_faire_customer
    LEFT JOIN (
        SELECT DISTINCT
            order_sku,
            parent_ns_item_number AS netsuite_item_number
        FROM DWH_DEV.PROD.BRAND_EBITDA_PARENT_COMPONENT_SKU_MAPPING
    )
        ON sku = order_sku
    GROUP BY ALL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY sku ORDER BY date DESC, item_name) = 1
    ORDER BY sku
),

faire_dbr AS (
    SELECT
        COALESCE(g.date, r.date) AS date,
        COALESCE(g.brand, r.brand) AS brand,
        'Faire' AS channel_name,
        COALESCE(g.customer_name, r.customer_name) AS faire_customer_name,
        COALESCE(g.sku, r.sku) AS faire_sku,
        SUM(COALESCE(g.gross_rev, 0)) AS faire_gross_rev,
        SUM(COALESCE(g.discounts, 0)) AS faire_discounts,
        SUM(COALESCE(g.shipping, 0)) AS faire_shipping,
        SUM(COALESCE(r.returns, 0)) AS faire_returns,
        faire_gross_rev
            + faire_discounts
            + faire_shipping
            + faire_returns AS faire_net_rev,
        COUNT(DISTINCT g.order_id) AS faire_orders,
        SUM(COALESCE(g.units_ordered, 0)) AS faire_units_ordered,
        SUM(COALESCE(r.units_returned, 0)) AS faire_units_returned,
        faire_units_ordered
            - faire_units_returned AS faire_net_units_sold
    FROM gross_rev_by_faire_customer AS g
    FULL JOIN returns_by_faire_customer AS r
        ON g.date = r.date
            AND g.brand = r.brand
            AND g.customer_name = r.customer_name
            AND g.sku = r.sku
    GROUP BY ALL
)

SELECT
    DATE_TRUNC('month', date) AS month,
    brand,
    channel_name,
    faire_customer_name,
    sku,
    netsuite_item_number,
    CASE WHEN sku IS NULL THEN 'Faire Commission Fee' ELSE m.item_name END AS item_name,
    SUM(faire_gross_rev) AS faire_gross_rev,
    SUM(faire_discounts) AS faire_discounts,
    SUM(faire_shipping) AS faire_shipping,
    SUM(faire_returns) AS faire_returns,
    SUM(faire_net_rev) AS faire_net_rev,
    SUM(faire_orders) AS faire_orders,
    SUM(faire_units_ordered) AS faire_units_ordered,
    SUM(faire_units_returned) AS faire_units_returned,
    SUM(faire_net_units_sold) AS faire_net_units_sold,
FROM faire_dbr
LEFT JOIN item_name_mapping AS m
    ON faire_sku = sku
WHERE date >= '2025-01-01'
GROUP BY ALL
ORDER BY
    month,
    brand,
    faire_customer_name,
    faire_net_rev DESC;
