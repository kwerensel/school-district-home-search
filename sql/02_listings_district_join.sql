-- Assign each listing point to the school district polygon that contains it.
-- Assumes listing points are in WGS84 and PA district polygons are in EPSG:3857.

DROP TABLE IF EXISTS listings_with_districts;

CREATE TABLE listings_with_districts AS
SELECT
    l.*,
    d."SCHOOL_NAM" AS school_district,
    d."CTY_NAME" AS county_name
FROM home_listings_points l
LEFT JOIN pa_school_districts d
    ON ST_Contains(
        d.geom,
        ST_Transform(l.geom, 3857)
    );
