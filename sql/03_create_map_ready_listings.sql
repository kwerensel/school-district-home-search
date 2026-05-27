DROP TABLE IF EXISTS listings_map_ready;

CREATE TABLE listings_map_ready AS
SELECT
    l.id,
    l.address,
    l.city,
    l.state,
    l.zip,
    l.price,
    l.beds,
    l.baths,
    l.url,
    l.school_district,
    l.county_name,
    CASE
        WHEN g.district_name IS NOT NULL THEN true
        ELSE false
    END AS good_district,
    l.geom
FROM listings_with_districts l
LEFT JOIN good_school_districts g
    ON l.school_district = g.district_name;

CREATE INDEX IF NOT EXISTS listings_map_ready_geom_idx
ON listings_map_ready
USING GIST (geom);
