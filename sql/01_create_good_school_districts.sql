DROP TABLE IF EXISTS good_school_districts;

CREATE TABLE good_school_districts (
    district_name text PRIMARY KEY
);

-- Replace with exact district names returned by your school district table.
INSERT INTO good_school_districts (district_name)
VALUES
('Haverford Township'),
('Lower Merion'),
('Upper Darby')
ON CONFLICT DO NOTHING;
