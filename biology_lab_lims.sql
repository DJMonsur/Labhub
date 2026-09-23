-- ============================================================
--  PSHS-CARC Biology Laboratory LIMS
--  Database: MySQL / MariaDB (SQL:2016 compatible)
--  Source: biobio1.xlsx  ·  Schema based on ERM in research paper
--  Generated for: Asirit, Espallardo & Garcia (2025)
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  DROP ORDER (children first)
-- ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS inventory_log;
DROP TABLE IF EXISTS borrow_record;
DROP TABLE IF EXISTS inventory_record;
DROP TABLE IF EXISTS item;
DROP TABLE IF EXISTS item_type;
DROP TABLE IF EXISTS location;
DROP TABLE IF EXISTS user;

-- ============================================================
--  1. LOCATION
--     Stores physical locations within the school.
-- ============================================================
CREATE TABLE location (
    location_id   INT            NOT NULL AUTO_INCREMENT,
    location_name VARCHAR(120)   NOT NULL,
    building      VARCHAR(80),
    room_code     VARCHAR(30),
    PRIMARY KEY (location_id)
);

-- ============================================================
--  2. ITEM_TYPE  (lookup / reference)
--     Normalises the "type" column – acts as a FK target.
-- ============================================================
CREATE TABLE item_type (
    type_id      SMALLINT       NOT NULL AUTO_INCREMENT,
    type_label   VARCHAR(60)    NOT NULL UNIQUE,   -- e.g. 'Slide/Histology'
    category     VARCHAR(40)    NOT NULL,           -- 'Equipment' | 'Material' | 'Slide'
    PRIMARY KEY (type_id)
);

-- ============================================================
--  3. USER
--     Matches the ERM in the research proposal.
-- ============================================================
CREATE TABLE user (
    user_id       INT            NOT NULL AUTO_INCREMENT,
    user_name     VARCHAR(100)   NOT NULL,
    user_email    VARCHAR(150)   NOT NULL UNIQUE,
    user_role     ENUM('student','teacher','lab_personnel','it_personnel') NOT NULL,
    password_hash VARCHAR(255)   NOT NULL,
    created_at    TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id)
);

-- ============================================================
--  4. ITEM
--     Master catalogue of every laboratory item.
--     References item_type for normalised type filtering.
-- ============================================================
CREATE TABLE item (
    item_id          INT            NOT NULL AUTO_INCREMENT,
    item_name        VARCHAR(200)   NOT NULL,
    type_id          SMALLINT       NOT NULL,   -- FK → item_type
    item_count       DECIMAL(12,3)  NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    unit             VARCHAR(20),               -- pcs / mL / grams / kit …
    item_description TEXT,
    is_borrowable    TINYINT(1)     NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id),
    CONSTRAINT fk_item_type FOREIGN KEY (type_id)
        REFERENCES item_type (type_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- ============================================================
--  5. INVENTORY_RECORD
--     Links each item to a location and tracks available stock.
--     Matches the ERM: record_id, item_id, location_id, available_count
-- ============================================================
CREATE TABLE inventory_record (
    record_id       INT  NOT NULL AUTO_INCREMENT,
    item_id         INT  NOT NULL,
    location_id     INT  NOT NULL,
    available_count DECIMAL(12,3) NOT NULL DEFAULT 0 CHECK (available_count >= 0),
    last_updated    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (record_id),
    UNIQUE KEY uq_item_location (item_id, location_id),
    CONSTRAINT fk_inv_item     FOREIGN KEY (item_id)
        REFERENCES item (item_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_inv_location FOREIGN KEY (location_id)
        REFERENCES location (location_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
--  6. BORROW_RECORD
--     Tracks every borrow / return transaction.
-- ============================================================
CREATE TABLE borrow_record (
    borrow_id        INT  NOT NULL AUTO_INCREMENT,
    user_id          INT  NOT NULL,
    item_id          INT  NOT NULL,
    location_id      INT  NOT NULL,
    quantity_borrowed DECIMAL(12,3) NOT NULL DEFAULT 1 CHECK (quantity_borrowed > 0),
    status           ENUM('pending','approved','borrowed','returned','cancelled')
                         NOT NULL DEFAULT 'pending',
    borrow_date      DATETIME,
    return_date      DATETIME,
    due_date         DATE,
    notes            TEXT,
    PRIMARY KEY (borrow_id),
    CONSTRAINT fk_borrow_user     FOREIGN KEY (user_id)
        REFERENCES user (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_borrow_item     FOREIGN KEY (item_id)
        REFERENCES item (item_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_borrow_location FOREIGN KEY (location_id)
        REFERENCES location (location_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
--  7. INVENTORY_LOG
--     Audit trail — matches the ERM exactly.
-- ============================================================
CREATE TABLE inventory_log (
    log_id      INT          NOT NULL AUTO_INCREMENT,
    user_id     INT          NOT NULL,
    item_id     INT          NOT NULL,
    action_type VARCHAR(30)  NOT NULL,  -- 'ADD','UPDATE','DELETE','BORROW','RETURN'
    old_value   TEXT,
    new_value   TEXT,
    timestamp   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id),
    CONSTRAINT fk_log_user FOREIGN KEY (user_id)
        REFERENCES user (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_log_item FOREIGN KEY (item_id)
        REFERENCES item (item_id)
        ON UPDATE CASCADE ON DELETE CASCADE
);


-- ============================================================
--  USEFUL VIEWS
-- ============================================================

-- Full inventory with type, location, availability
CREATE OR REPLACE VIEW v_inventory AS
SELECT
    ir.record_id,
    i.item_id,
    i.item_name,
    it.category,
    it.type_label  AS item_type,
    i.unit,
    i.item_count   AS total_count,
    ir.available_count,
    (i.item_count - ir.available_count) AS borrowed_count,
    l.location_name,
    i.item_description,
    i.is_borrowable,
    ir.last_updated
FROM inventory_record ir
JOIN item             i   ON i.item_id     = ir.item_id
JOIN item_type        it  ON it.type_id    = i.type_id
JOIN location         l   ON l.location_id = ir.location_id;

-- Active borrows (not yet returned)
CREATE OR REPLACE VIEW v_active_borrows AS
SELECT
    br.borrow_id,
    u.user_name,
    u.user_role,
    i.item_name,
    it.type_label  AS item_type,
    br.quantity_borrowed,
    br.status,
    br.borrow_date,
    br.due_date,
    l.location_name
FROM borrow_record br
JOIN user      u  ON u.user_id    = br.user_id
JOIN item      i  ON i.item_id    = br.item_id
JOIN item_type it ON it.type_id   = i.type_id
JOIN location  l  ON l.location_id = br.location_id
WHERE br.status IN ('approved','borrowed');


-- ============================================================
--  SEED DATA
-- ============================================================

-- ── LOCATION ─────────────────────────────────────────────────
INSERT INTO location (location_name, building, room_code) VALUES
  ('Biology Lab', 'Science Building', 'BIO-LAB-01');

-- ── ITEM TYPES ───────────────────────────────────────────────
INSERT INTO item_type (type_label, category) VALUES
  ('Equipment',                     'Equipment'),
  ('Equipment/Anatomical Model',    'Equipment'),
  ('Material/Consumable',           'Material'),
  ('Material/PCR Supply',           'Material'),
  ('Material/Microbiological Media','Material'),
  ('Slide/Kingdom Protista',        'Slide'),
  ('Slide/Kingdom Fungi',           'Slide'),
  ('Slide/Kingdom Bacteria',        'Slide'),
  ('Slide/Kingdom Plantae',         'Slide'),
  ('Slide/Kingdom Animalia',        'Slide'),
  ('Slide/Microbiology',            'Slide'),
  ('Slide/Human Bacteria',          'Slide'),
  ('Slide/Histology',               'Slide'),
  ('Slide/Various Prepared',        'Slide');

-- ── DEMO USERS ───────────────────────────────────────────────
INSERT INTO user (user_name, user_email, user_role, password_hash) VALUES
  ('Admin Personnel',  'admin@pshs-carc.edu.ph',   'lab_personnel', 'HASH_PLACEHOLDER'),
  ('IT Admin',         'it@pshs-carc.edu.ph',       'it_personnel',  'HASH_PLACEHOLDER'),
  ('Sample Teacher',   'teacher@pshs-carc.edu.ph',  'teacher',       'HASH_PLACEHOLDER'),
  ('Sample Student',   'student@pshs-carc.edu.ph',  'student',       'HASH_PLACEHOLDER');

-- ── ITEMS (549 records) ──────────────────────────────────────
-- Format: (item_name, type_id, item_count, unit)
-- type_id key:
--   1=Equipment  2=Equipment/Anatomical Model  3=Material/Consumable
--   4=Material/PCR Supply  5=Material/Microbiological Media
--   6=Slide/Kingdom Protista  7=Slide/Kingdom Fungi
--   8=Slide/Kingdom Bacteria  9=Slide/Kingdom Plantae
--  10=Slide/Kingdom Animalia  11=Slide/Microbiology
--  12=Slide/Human Bacteria  13=Slide/Histology  14=Slide/Various Prepared

INSERT INTO item (item_name, type_id, item_count, unit) VALUES
-- ── EQUIPMENT ────────────────────────────────────────────────
('Agar Slant Rack', 1, 2, 'pcs'),
('Alcohol Lamp, 100 mL', 1, 27, 'pcs'),
('Autoclave', 1, 1, 'unit'),
('Beaker, 50 mL', 1, 27, 'pcs'),
('Beaker, 150mL', 1, 22, 'pcs'),
('Beaker, 250 mL', 1, 11, 'pcs'),
('Beaker, 400 mL', 1, 11, 'pcs'),
('Beaker, 500 mL', 1, 5, 'pcs'),
('Beaker, 600 mL', 1, 2, 'pcs'),
('Beaker, 1000 mL', 1, 13, 'pcs'),
('Beaker, Jug Type, 1000 mL', 1, 4, 'pcs'),
('Binocular Microscope, Labomed', 1, 3, 'unit'),
('Binocular Microscope, Motic', 1, 6, 'unit'),
('Binocular Microscope, Kerm Optic', 1, 1, 'unit'),
('Biosafety Cabinet', 1, 1, 'unit'),
('Centrifuge (Low Speed)', 1, 1, 'unit'),
('Centrifuge Tube, Conical, 15mL', 1, 94, 'pcs'),
('Centrifuge Tube, PP, 13 mL', 1, 72, 'pcs'),
('Colony Counter', 1, 1, 'unit'),
('Cover Slips', 1, 23, 'box'),
('Dissecting Kit', 1, 5, 'kit'),
('Dissecting Needle', 1, 87, 'pcs'),
('Dissecting Pan', 1, 25, 'pcs'),
('Dissecting Insect Pin, Small', 1, 90, 'pcs'),
('Droppers', 1, 175, 'pcs'),
('Durham Tubes/Fermentation tubes', 1, 180, 'pcs'),
('Dual Sex Torso', 1, 1, 'set'),
('Erlenmeyer Flask, 100 mL', 1, 30, 'pcs'),
('Erlenmeyer Flask, 250 mL', 1, 13, 'pcs'),
('Erlenmeyer Flask, 500 mL', 1, 26, 'pcs'),
('Erlenmeyer Flask, 1000 mL', 1, 13, 'pcs'),
('Erlenmeyer Flask, PP, 1000 mL', 1, 2, 'pcs'),
('Evaporating Dish', 1, 16, 'pcs'),
('Eyepiece Micrometer, 10mm/100 div', 1, 26, 'pcs'),
('Forceps', 1, 55, 'pcs'),
('Funnel, Plastic', 1, 10, 'pcs'),
('Fumehood', 1, 1, 'unit'),
('Glass Slide', 1, 11, 'box'),
('Glass Slide, Single Concave', 1, 30, 'pcs'),
('Glass Slide, Double Concave', 1, 25, 'pcs'),
('Graduated Cylinder, 10 mL', 1, 31, 'pcs'),
('Graduated Cylinder, 25 mL', 1, 8, 'pcs'),
('Graduated Cylinder, 50 mL', 1, 5, 'pcs'),
('Graduated Cylinder, 100mL', 1, 16, 'pcs'),
('Guaze Iron Wire, Ceramic Center', 1, 27, 'pcs'),
('Hotplate, Ceramic', 1, 6, 'pcs'),
('HD VGA Camera for Microscope HDL', 1, 1, 'unit'),
('Inoculation Loop', 1, 86, 'pcs'),
('Inoculating Needle', 1, 33, 'pcs'),
('Inverted Microscope Trinocular Head', 1, 1, 'unit'),
('Laboratory Incubator', 1, 1, 'unit'),
('Laboratory Incubator, Forced Convection', 1, 1, 'unit'),
('Laboratory Oven', 1, 1, 'unit'),
('Laboratory Refrigerator', 1, 1, 'set'),
('Magnetic Retriever', 1, 2, 'pcs'),
('Magnetic Stirring Bar', 1, 15, 'pcs'),
('Magnifying glass, 80-100 mm', 1, 9, 'pcs'),
('Micropipette, Adjustable Volume, 20-200 uL', 1, 2, 'pcs'),
('Micropipette, Adjustable Volume, 10-100 uL', 1, 2, 'pc'),
('Micropipette, Adjustable Volume, 0.5-10 uL', 1, 2, NULL),
('Micropipette, Adjustable Volume, 100 to 1000 uL', 1, 2, NULL),
('Micrometer Stage, 1 DIV = 0.01 mm', 1, 14, 'pcs'),
('Microscope Objectives, 4X', 1, 19, 'pcs'),
('Microscope Objective, 10X', 1, 20, 'pcs'),
('Microscope Objective, 60x', 1, 13, 'pcs'),
('Microscope Objective, 100x', 1, 12, 'pcs'),
('Microtubes, 1.5mL', 1, 2, 'pack'),
('Microtubes for PCR', 1, 1, 'pack'),
('Monocular Biological Microscope', 1, 10, 'unit'),
('Pasteur Pipette, Glass, 230 mm', 1, 175, 'pcs'),
('Petri Dish, 100 mm x 15 mm', 1, 525, 'pcs'),
('Pipette, Graduated, 10 mL', 1, 23, 'pcs'),
('Pipette pump, 10mL', 1, 16, 'pcs'),
('Pipette pump, 25mL', 1, 2, 'pcs'),
('Scalpel Holder', 1, 17, 'pcs'),
('Scissors, Curved', 1, 6, 'pcs'),
('Scissors, Straight', 1, 14, 'pcs'),
('Screw Cap Tube, 10 mL', 1, 25, 'pcs'),
('Screw Cap Tube, 15 mL', 1, 345, 'pcs'),
('Screw Cap Tube, 20 mL', 1, 72, 'pcs'),
('Slide Box, 100 holder', 1, 9, 'pcs'),
('Slide Box, 25 holder', 1, 2, 'pcs'),
('Slide Box, 50 holder', 1, 9, 'pcs'),
('Spinbar, Octagon', 1, 32, 'pcs'),
('Spatula, Wooden Handle', 1, 32, 'pcs'),
('Spoonula, Metal', 1, 5, 'pcs'),
('Spreader for Bacterial Inoculum', 1, 20, 'pcs'),
('Staining Rack', 1, 4, 'pcs'),
('Stirring Rod, Glass', 1, 12, 'pcs'),
('Stirring Rod, Plastic Coated', 1, 4, 'pcs'),
('Test Tube, 13x100mm, 10mL', 1, 191, 'pcs'),
('Test Tube, 15 mL to 20 mL', 1, 219, 'pcs'),
('Testtube Brush', 1, 37, 'pcs'),
('Test tube, holder, metal', 1, 30, 'pcs'),
('Testtube Rack, PP Material', 1, 5, 'set'),
('Testtube Rack, Wood', 1, 31, 'pcs'),
('Thermometer, Red Liquid, Scale C', 1, 32, 'pcs'),
('Tripod, 6"H, Black Enameled Cast Iron', 1, 10, 'pcs'),
('Vernier Caliper', 1, 12, 'pcs'),
('Volumetric Flask, 100mL', 1, 8, 'pcs'),
('Volumetric Flask, 250mL', 1, 9, 'pcs'),
('Wash Bottle, 250 mL', 1, 19, 'pcs'),
('Watch glass, high-quality flint glass', 1, 19, 'pcs'),
('Water through, Metal', 1, 16, 'pcs'),
('Stool', 1, 30, 'pcs'),
-- ── MATERIAL / CONSUMABLE ────────────────────────────────────
('Alcohol, ethyl alcohol, 95%', 3, 4, 'gal'),
('Alcohol, ethyl alcohol, 70% solution', 3, 4, 'gal'),
('Alcohol, 70%, isopropyl alcohol', 3, 4, 'gal'),
('Aluminum Foil', 3, 2, 'roll'),
('Aluminum Tray', 3, 26, 'pcs'),
('Anti-A Serum', 3, 2, 'bottle'),
('Anti-B Serum', 3, 2, 'bottle'),
('Anti-D Serum', 3, 2, 'bottle'),
('Autoclave bags, at least 24x36"', 3, 5, 'pack'),
('Autoclave bags, 8 1/2 x 11', 3, 1, 'pack'),
('Baby wipes', 3, 3, 'packs'),
('Bar soap, germicidal', 3, 5, 'bar'),
('Blood Lancet, 200pcs/box', 3, 6, 'box'),
('Cotton roll', 3, 11, 'roll'),
('Cover glass', 3, 10, 'box'),
('Deionized water, 1L/btl', 3, 10, 'btl'),
('Denatured Alcohol, 1L/btl', 3, 13, 'btl'),
('Detergent powder', 3, 1, 'Kilo'),
('Dishwashing liquid', 3, 6, 'Liters'),
('Disinfectant cleaner, 900mL/btl', 3, 2, 'Btl'),
('Distilled Water, 5L/btl', 3, 23, 'Btl'),
('Face mask, Disposable', 3, 13, 'box'),
('Face mask, N95', 3, 2, 'pcs'),
('First Aid Kit, Wooden Cabinet', 3, 1, 'kit'),
('Gauze bandage, 4"x10yards', 3, 8, 'rolls'),
('Gloves, Heat-resistant', 3, 1, 'pairs'),
('Gloves, nitrile, single use, powder free, non-sterile', 3, 3, 'box'),
('Hand soap, liquid, 1L/btl', 3, 3, 'btl'),
('Laboratory Coat, Black', 3, 1, 'pc'),
('Laboratory Coat, Shoes', 3, 1, 'pair'),
('Laboratory film, 4in x 125 ft/roll', 3, 2, 'roll'),
('Lens cleaning tissue, 10 x 15cm', 3, 5, 'booklet'),
('Lighter, long nozzle, kitchen/utility gas lighter', 3, 5, 'pcs'),
('Liquid hand soap, antibacterial, 900mL/btl', 3, 2, NULL),
('Microscope slides, clear glass, unground edges, 1" x 3", 1mm-1.2mm thick, 72pcs/box', 3, 12, 'box'),
('Molecular Biology Starter Package', 3, 1, 'set'),
('Oil Immersion/immersion oil', 3, 30, 'mL'),
('PCR Lab Starter Package', 3, 1, 'set'),
('Pipette tips, 10uL tip, VolRange 0.1-10uL', 3, 7, 'pack'),
('Pipette tips, 200uL tip, VolRange 2-200uL', 3, 14, 'pack'),
('Pipette tips, 1000uL tip, VolRange 100-1000uL', 3, 1, 'pack'),
('Pipette tips, 500uL tip, VolRange 1-5mL', 3, 2, 'pack'),
('Pipette tips, VolRange 1-10mL', 3, 2, 'pack'),
('Pipette tips, 200uL, yellow', 3, 1, 'pack'),
('Powdered Detergent', 3, 1, 'kg'),
('Rubberband', 3, 1, 'box'),
('Scrub Suit', 3, 2, 'pcs'),
('Surgical Blades, 100pcs/box', 3, 5, 'box'),
('Syringe with needle, single use, 5 cc/mL, 100pcs/box', 3, 14, 'box'),
('Syringe with needle, single use, 10 cc/mL, 100pcs/box', 3, 14, 'box'),
('Task wipers, 4.3x8.4in', 3, 3, 'box'),
('Tissue, bathroom, 2 ply, 12 rolls/pack', 3, 3, 'pack'),
('Tongue Depressor / wooden TD', 3, 3, 'box'),
('Water Dispenser', 3, 1, 'unit'),
('Wax paper', 3, 2, 'roll'),
('Wooden cotton applicator, sterile, 6"', 3, 4, 'box'),
('Wooden tongue depressor, sterile, 6"', 3, 2, 'box'),
-- ── MATERIAL / PCR SUPPLY ────────────────────────────────────
('DNA Ladder, 1Kb, 500uL (100 lanes)', 4, 2, 'kit'),
('Nylon Membrane filter, pore size 0.45 micrometer, 47mm diameter, pack of 100', 4, 2, 'kit'),
('Flapure Bacteria Genomic DNA Extraction Kit', 4, 2, 'kit'),
('GF-1 Bacterial DNA Extraction Kit', 4, 1, 'box'),
('Sartorius Biolab Product', 4, 5, 'box'),
('Nuclease Free water (ultra pure grade), 500mL/btl', 4, 1, 'btl'),
('10x Tris-acetate-EDTA (TAE) Buffer, pH8.0 (Ultra pure grade)', 4, 1, 'btl'),
('Agarose (Molecular Biology Grade), 500g/btl', 4, 2, 'btl'),
('Water (Biotechnology grade), 1L/btl', 4, 1, 'btl'),
-- ── MATERIAL / MICROBIOLOGICAL MEDIA ─────────────────────────
('Chromocult coliform agar', 5, 500, 'grams'),
('EMB Agar', 5, 1000, 'grams'),
('Lactose Broth', 5, 996, 'grams'),
('MacConkey Agar', 5, 1500, 'grams'),
('Mannitol Salt Agar', 5, 500, 'grams'),
('Mannitol Salt Agar Base', 5, 805, 'grams'),
('Mueller Hinton Agar', 5, 822, 'grams'),
('Mueller Hinton Broth', 5, 500, 'grams'),
('Nutrient Agar', 5, 500, 'grams'),
('Nutrient Broth', 5, 1333, 'grams'),
('Peptone, Bacteriological', 5, 1000, 'grams'),
('Plate Count Agar', 5, 500, 'grams'),
('Potato Dextrose Agar', 5, 488, 'grams'),
('Potato Dextrose Broth', 5, 1500, 'grams'),
('Sabouraud Dextrose Agar', 5, 1000, 'grams'),
('Simmon Citrate Agar', 5, 491, 'grams'),
('Tryptone Broth (500g)', 5, 478, 'grams'),
('Simmons Citrate Agar', 5, 500, 'grams'),
('Tryptone Broth (500g/btl)', 5, 500, 'grams'),
-- ── SLIDE / KINGDOM PROTISTA ─────────────────────────────────
('Acanthamoeba', 6, 2, 'pcs'),
('Amoeba proteus, w.m', 6, 1, 'pcs'),
('Amoeba, w.m', 6, 1, 'pcs'),
('Balantidium coli trophozoite, w.m', 6, 12, 'pcs'),
('Chilomastix mesneli troph, w.m', 6, 2, 'pcs'),
('Diatoms, marine, w.m', 6, 12, 'pcs'),
('Entamoeba coli cysts smear', 6, 1, 'pc'),
('Entamoeba histolytica trophozite', 6, 11, 'pcs'),
('Euglena, w.m', 6, 9, 'pcs'),
('Foraminifera, w.m', 6, 10, 'pcs'),
('Giardia lamblia cyst, w.m', 6, 2, 'pcs'),
('Giardia lamblia trophozoite, w.m', 6, 12, 'pcs'),
('Monocystis, w.m', 6, 2, 'pcs'),
('Paramecium fission mass, w.m', 6, 10, 'pcs'),
('Paramecium in conjugation, w.m', 6, 12, 'pcs'),
('Paramecium plain, w.m', 6, 11, 'pcs'),
('Radiolaria, w.m', 6, 12, 'pcs'),
('Trypanosome, Blood', 6, 10, 'pcs'),
-- ── SLIDE / KINGDOM FUNGI ────────────────────────────────────
('Aspergillus niger spores', 7, 10, 'pcs'),
('Basidiospores, w.m', 7, 10, 'pcs'),
('Candida albicans chlamydoconidia', 7, 10, 'pcs'),
('Candida albicans pseudophyta', 7, 10, 'pcs'),
('Candida albicans, smear', 7, 12, 'pcs'),
('Crytococcus blastoconidia', 7, 10, 'pcs'),
('Lichen, c.s', 7, 10, 'pcs'),
('Mucor indicus, w.m', 7, 10, 'pcs'),
('Mycophyta mucor, w.m', 7, 13, 'pcs'),
('Penicillium chrysogenum spores', 7, 10, 'pcs'),
('Penicillium, w.m', 7, 12, 'pcs'),
('Rhizopus sporangia, w.m', 7, 12, 'pcs'),
('Saccharomyces cerevisiae, smear', 7, 13, 'pcs'),
('Yeast budding, smear', 7, 12, 'pcs'),
-- ── SLIDE / KINGDOM BACTERIA ─────────────────────────────────
('Bacillus', 8, 10, 'pcs'),
('Bacillus subtilis', 8, 12, 'pcs'),
('Clostridium botulinum', 8, 12, 'pcs'),
('Coccobacilli', 8, 10, 'pcs'),
('Coccus smear', 8, 9, 'pcs'),
('Diplobacillus', 8, 10, 'pcs'),
('Diplococcus', 8, 10, 'pcs'),
('Diplococcus pneumoniae', 8, 12, 'pcs'),
('Escherichia coli', 8, 12, 'pcs'),
('Human Bacterial Slides', 8, 25, 'pcs'),
('Klebsiella pneumoniae, smear', 8, 12, 'pcs'),
('Moruxella cattarhalis, smear', 8, 2, 'pcs'),
('Proteus vulgaris', 8, 12, 'pcs'),
('Pseudomonas aeruginosa', 8, 12, 'pcs'),
('Rhizobium sec of root', 8, 2, 'pcs'),
('Rhizobium, smear', 8, 10, 'pcs'),
('Salmonella typhosa', 8, 12, 'pcs'),
('Sarcina lutea', 8, 10, 'pcs'),
('Serratia marcecens', 8, 11, 'pcs'),
('Spirillum', 8, 9, 'pcs'),
('Spirillum lanatum, smear', 8, 10, 'pcs'),
('Staphylococcus', 8, 10, 'pcs'),
('Streptococcus', 8, 21, 'pcs'),
('Streptococcus pyogenes', 8, 10, 'pcs'),
('Vibrio', 8, 10, 'pcs'),
('Vibrio coma', 8, 12, 'pcs'),
-- ── SLIDE / KINGDOM PLANTAE ──────────────────────────────────
('Allium cepa root tip, c.s', 9, 11, 'pcs'),
('Allium cepa root tip, l.s', 9, 12, 'pcs'),
('Angle C.S moss spore capsule', 9, 10, 'pcs'),
('Angle moss fronds Section', 9, 10, 'pcs'),
('Chlamydomonas, w.m', 9, 12, 'pcs'),
('Chloroplast', 9, 10, 'pcs'),
('Cogon leaf monocot, c.s', 9, 20, 'pcs'),
('Cucurbita stem, c.s', 9, 10, 'pcs'),
('Dicot ficus leaf, c.s', 9, 12, 'pcs'),
('Fern leaf with sporangia', 9, 2, 'pcs'),
('Fern leaf, c.s', 9, 10, 'pcs'),
('Fern prothalium mature sporophyte, w.m', 9, 1, 'pcs'),
('Fern prothalium, w.m', 9, 10, 'pcs'),
('Fern sporangia, w.m', 9, 9, 'pcs'),
('Fern young sporophyte, w.m', 9, 12, 'pcs'),
('Funaria archegonial, l.s', 9, 10, 'pcs'),
('Funaria blade, w.m', 9, 10, 'pcs'),
('Funaria Overall, w.m', 9, 10, 'pcs'),
('Funaria sperm, l.s', 9, 10, 'pcs'),
('Funaria Stem', 9, 10, 'pcs'),
('Funaria T.S leaf', 9, 10, 'pcs'),
('Glandular trichomes, w.m', 9, 12, 'pcs'),
('Gourd moss spore capsule, l.s', 9, 10, 'pcs'),
('Gourd Protonema, w.m', 9, 10, 'pcs'),
('Helianthus young stem, c.s', 9, 10, 'pcs'),
('Hibiscus, young stem, c.s', 9, 5, 'pcs'),
('Hornworts overall, w.m', 9, 10, 'pcs'),
('Liverworts fronds Section', 9, 10, 'pcs'),
('Liverworts gemma cup', 9, 10, 'pcs'),
('Liverworts gemma, w.m', 9, 10, 'pcs'),
('Liverworts sporophyte, l.s', 9, 10, 'pcs'),
('Phloem with companion cells, l.s', 9, 12, 'pcs'),
('Pinewood, c.s', 9, 10, 'pcs'),
('Pollen grains, mixed, w.m', 9, 12, 'pcs'),
('Sambucus stem apex, dicot, l.s', 9, 5, 'pcs'),
('Scale trichomes, w.m', 9, 12, 'pcs'),
('Taraxacum, dandelion', 9, 10, 'pcs'),
('Vessel elements, w.m', 9, 12, 'pcs'),
('Volvox (Green algae), w.m', 9, 11, 'pcs'),
('Xylem (Ranunculus), c.s', 9, 11, 'pcs'),
('Xylem (Ranunculus), young & old root, c.s', 9, 1, 'pcs'),
('Xylem (Ranunculus), young root, c.s', 9, 1, 'pcs'),
('Zea mays (Corn) old stem, c.s', 9, 4, 'pcs'),
('Zea mays (Corn) young stem, c.s', 9, 13, 'pcs'),
('Zea mays stem, l.s', 9, 12, 'pcs'),
-- ── SLIDE / KINGDOM ANIMALIA ─────────────────────────────────
('Artery and vein, c.s', 10, 10, 'pcs'),
('Axillary skin, Human, c.s', 10, 10, 'pcs'),
('Blood, RBC, Human smear', 10, 12, 'pcs'),
('Blood, WBC, Human, smear', 10, 11, 'pcs'),
('Brown Skin, HUMAN', 10, 12, 'pcs'),
('Cardiac muscle', 10, 6, 'pcs'),
('Colon, Mammal', 10, 10, 'pcs'),
('Columnar Epithelium, (FROG), sect.', 10, 5, 'pcs'),
('Cuboidal epithelium', 10, 5, 'pcs'),
('Earthworm, Middle, c.s', 10, 12, 'pcs'),
('Embryo of mouse', 10, 10, 'pcs'),
('Esophagus, Mammal, c.s', 10, 10, 'pcs'),
('Frog early blastula, c.s', 10, 10, 'pcs'),
('Frog early gastrula, c.c', 10, 12, 'pcs'),
('Frog late blastula, c.s', 10, 2, 'pcs'),
('Frog late gastrula, sec', 10, 12, 'pcs'),
('Frog liver section', 10, 10, 'pcs'),
('Human chromosome', 10, 10, 'pcs'),
('Hydra plain w.m', 10, 8, 'pcs'),
('Hydra with bud w.m', 10, 12, 'pcs'),
('Large intestine c.s', 10, 10, 'pcs'),
('Liver cirrhosis', 10, 10, 'pcs'),
('Liver, cat, c.s', 10, 10, 'pcs'),
('Liver, frog, sect', 10, 2, 'pcs'),
('Liver, pig, c.s', 10, 10, 'pcs'),
('Mammal nerve c.s', 10, 10, 'pcs'),
('Mitochondria, sect', 10, 10, 'pcs'),
('Neuron smear', 10, 10, 'pcs'),
('Pancreas, Human, c.s', 10, 10, 'pcs'),
('Sebaceous gland (SKIN) c.s', 10, 10, 'pcs'),
('Simple Columnar epithelium', 10, 11, 'pcs'),
('Simple squamous epithelium, FROG', 10, 7, 'pcs'),
('Simple squamous epithelium, HUMAN, smear', 10, 5, 'pcs'),
('Skin, Frog, c.s', 10, 11, 'pcs'),
('Small intestine c.s', 10, 9, 'pcs'),
('Smooth muscle, l.s & c.s', 10, 8, 'pcs'),
('Sperm smear', 10, 7, 'pcs'),
('Spinal cord, Mammal. C.s', 10, 10, 'pcs'),
('Stomach, Fundic, Human, c.s', 10, 12, 'pcs'),
('Stratified squamous epithelium, MAMMAL', 10, 6, 'pcs'),
('Striated muscle, l.s', 10, 5, 'pcs'),
('Villi l.s', 10, 11, 'pcs'),
-- ── SLIDE / MICROBIOLOGY ─────────────────────────────────────
('Actinomycete w.m.', 11, 1, 'pc'),
('Bacillus anthracis Smear', 11, 1, 'pc'),
('Bacillus pertussis Smear', 11, 1, 'pc'),
('Bacillus pestis', 11, 1, 'pc'),
('Campylobacter jejuni', 11, 1, 'pc'),
('Capsul (Pneumonia)', 11, 1, 'pc'),
('Clostridium botulinum Smear', 11, 1, 'pc'),
('Clostridium tetani Smear', 11, 1, 'pc'),
('Corynebacterium diphtheriae Smear', 11, 1, 'pc'),
('Dysentery Bacillus Smear', 11, 1, 'pc'),
('Escherichia coli Smear', 11, 1, 'pc'),
('Lactobacillus', 11, 1, 'pc'),
('Leptospira', 11, 1, 'pc'),
('Listeria Smear', 11, 1, 'pc'),
('Lophotrichous (green pus)', 11, 1, 'pc'),
('Meningococcal Smear', 11, 1, 'pc'),
('Penicillium w.m.', 11, 1, 'pc'),
('Peritrichous (Silver Staining - Typhia)', 11, 1, 'pc'),
('Pneumococcal Smear', 11, 1, 'pc'),
('Rhizopus stolonifer w.m.', 11, 1, 'pc'),
('Salmonella gallinarum Smear', 11, 1, 'pc'),
('Salmonella typhi Smear', 11, 1, 'pc'),
('Single flagellum (green pus)', 11, 1, 'pc'),
('Spore', 11, 1, 'pc'),
('Tetrads Smear', 11, 1, 'pc'),
-- ── SLIDE / HUMAN BACTERIA ───────────────────────────────────
('Acetic Acid Bacteria Smear', 12, 1, 'pc'),
('Actinomycetes', 12, 1, 'pc'),
('Actinomycetes installed piece', 12, 1, 'pc'),
('Albicans Cocci Smear', 12, 1, 'pc'),
('Aureus Smear', 12, 1, 'pc'),
('Bacillus Anthracis Smear', 12, 1, 'pc'),
('Bacillus Subtilis Smear', 12, 1, 'pc'),
('Bacteria in the Yogurt Chain Smear', 12, 1, 'pc'),
('Bacterial Type of Smear', 12, 1, 'pc'),
('Bordetella pertussis Smear', 12, 1, 'pc'),
('Cryptococcus Neoformans Fitted Sheet', 12, 1, 'pc'),
('Diptheria Bacilli Smear', 12, 1, 'pc'),
('Eight Stacked Cocci Smear', 12, 1, 'pc'),
('Escherichia Coli Smear', 12, 1, 'pc'),
('Golden Yellow Staphylococcus Smear', 12, 1, 'pc'),
('Gonorrhoeae Cocci Smear', 12, 1, 'pc'),
('Human Oral Bacteria Smear', 12, 1, 'pc'),
('Mycobacterium Tuberculosis Smear', 12, 1, 'pc'),
('Neisseria Gonorrhoeae Smear', 12, 1, 'pc'),
('Ordinary Deformation of a Bacterial Smear', 12, 1, 'pc'),
('Perfringens Bacilli Smear', 12, 1, 'pc'),
('Proteus Bacilli Smear', 12, 1, 'pc'),
('Pseudomonas Aeruginosa Smear', 12, 1, 'pc'),
('Quadruple Cocci Smear', 12, 1, 'pc'),
('Shigella Fitted Sheet', 12, 1, 'pc'),
('Tetanus Bacilli Smear', 12, 1, 'pc'),
('Thuringiensis Bacillus Smear', 12, 1, 'pc'),
('Typhoid Bacillus Smear', 12, 1, 'pc'),
('Vibrio Cholerae Fitted Sheet', 12, 1, 'pc'),
('Yellow Micro-cocci Smear', 12, 1, 'pc'),
-- ── SLIDE / HISTOLOGY ────────────────────────────────────────
('Adipose tissue', 13, 2, 'pc'),
('Adrenal gland c.s.', 13, 2, 'pc'),
('Aorta c.s.', 13, 2, 'pc'),
('Artery c.s.', 13, 2, 'pc'),
('Axillary skin vs', 13, 2, 'pc'),
('Bone decalcified c.s.', 13, 2, 'pc'),
('Cardiac muscle c.s.', 13, 2, 'pc'),
('Cardiac stomach, c.s.', 13, 2, 'pc'),
('Cat Ovary c.s.', 13, 2, 'pc'),
('Cerebellum H&e, c.s.', 13, 2, 'pc'),
('Cerebrum Ag stain, c.s.', 13, 2, 'pc'),
('Chick blood smear', 13, 2, 'pc'),
('Cochlea, c.s.', 13, 2, 'pc'),
('Columnar epithelium', 13, 2, 'pc'),
('Cuboidal epithelium (histology)', 13, 2, 'pc'),
('Duodenum, c.s.', 13, 2, 'pc'),
('Elastic cartilage', 13, 2, 'pc'),
('Embryonic connective tissue', 13, 2, 'pc'),
('Epididymis c.s. of human', 13, 2, 'pc'),
('Eye (Iris) of Cat, c.s.', 13, 2, 'pc'),
('Eyelid, human, c.s.', 13, 2, 'pc'),
('Fallopian tube c.s. (Oviduct)', 13, 2, 'pc'),
('Fibrocartilage c.s.', 13, 2, 'pc'),
('Frog blood smear', 13, 2, 'pc'),
('Frog ovary c.s.', 13, 2, 'pc'),
('Frog skin v.s.', 13, 2, 'pc'),
('Frog Small intestine c.s.', 13, 2, 'pc'),
('Frog stomach, c.s.', 13, 2, 'pc'),
('Fundis stomach section', 13, 2, 'pc'),
('Human Blood smear', 13, 2, 'pc'),
('Human brown skin, v.s.', 13, 2, 'pc'),
('Human esophagus, upper region c.s.', 13, 2, 'pc'),
('Human hair w.m.', 13, 2, 'pc'),
('Human Kidney c.s.', 13, 2, 'pc'),
('Human Large intestine, c.s.', 13, 2, 'pc'),
('Human Liver, c.s.', 13, 2, 'pc'),
('Human Lung, c.s.', 13, 2, 'pc'),
('Human ovary, c.s.', 13, 2, 'pc'),
('Human Pancreas, c.s.', 13, 2, 'pc'),
('Human pituitary gland, c.s.', 13, 2, 'pc'),
('Human Placenta c.s.', 13, 2, 'pc'),
('Human scalp l.s.', 13, 2, 'pc'),
('Human scalp v.s.', 13, 2, 'pc'),
('Human Sperm smear', 13, 2, 'pc'),
('Human Spleen c.s.', 13, 2, 'pc'),
('Human Squamous epithelium', 13, 2, 'pc'),
('Human Testis, c.s.', 13, 2, 'pc'),
('Human Vagina, c.s.', 13, 2, 'pc'),
('Hyaline cartilage', 13, 2, 'pc'),
('Ileum of human c.s.', 13, 2, 'pc'),
('Jejunum, c.s.', 13, 2, 'pc'),
('Large intestine-rectum, c.s.', 13, 2, 'pc'),
('Lips mammal l.s.', 13, 2, 'pc'),
('Lymph gland', 13, 2, 'pc'),
('Mammal tongue, c.s.', 13, 2, 'pc'),
('Mammal tooth developing, l.s.', 13, 2, 'pc'),
('Mammary gland, active human cs.', 13, 2, 'pc'),
('Mucoid tissue', 13, 2, 'pc'),
('Negro-white skin, l.s.', 13, 2, 'pc'),
('Nerve l.s.', 13, 2, 'pc'),
('Omentum, w.m.', 13, 2, 'pc'),
('Pacinian corpuscle, sec', 13, 2, 'pc'),
('Parotid gland c.s.', 13, 2, 'pc'),
('Penis c.s. of adult', 13, 2, 'pc'),
('Pseudo-stratified columnar ciliated epithelium', 13, 2, 'pc'),
('Pyloric stomach c.s.', 13, 2, 'pc'),
('Rabbit blood smear', 13, 2, 'pc'),
('Reticular tissue (lymph node)', 13, 2, 'pc'),
('Sciatic nerve c.s.', 13, 2, 'pc'),
('Seminal vesicle human cs', 13, 2, 'pc'),
('Smooth muscle section', 13, 2, 'pc'),
('Soft palate, human sec', 13, 2, 'pc'),
('Spinal cord l.s. from cow', 13, 2, 'pc'),
('Spinal cord, mammal c.s.', 13, 2, 'pc'),
('Stratified Squamous epithelium (histology)', 13, 2, 'pc'),
('Striated muscle c.s.', 13, 2, 'pc'),
('Striated muscle Frog, l.s.', 13, 2, 'pc'),
('Striated muscle l.s.', 13, 2, 'pc'),
('Submaxillary gland, c.s.', 13, 2, 'pc'),
('Sympathetic ganglion human, l.s.', 13, 2, 'pc'),
('Tendon and muscle, l.s.', 13, 2, 'pc'),
('Tendon spindle sensory nerve endings', 13, 2, 'pc'),
('Testis Frog, c.s.', 13, 2, 'pc'),
('Testis, mouse, c.s.', 13, 2, 'pc'),
('Toad skin', 13, 2, 'pc'),
('Tongue Frog c.s.', 13, 2, 'pc'),
('Tongue human, c.s.', 13, 2, 'pc'),
('Tooth in situ, cat', 13, 2, 'pc'),
('Trachea mammal, c.s.', 13, 2, 'pc'),
('Transitional epithelium', 13, 2, 'pc'),
('Umbilical cord, c.s.', 13, 2, 'pc'),
('Ureter, c.s.', 13, 2, 'pc'),
('Urinary bladder, human sec.', 13, 2, 'pc'),
('Uterus human (proliferative phase) sec.', 13, 2, 'pc'),
('Uterus human (secretory phase) cs', 13, 2, 'pc'),
('Utrethra female, c.s.', 13, 2, 'pc'),
('Vas deferens c.s.', 13, 2, 'pc'),
('Vein c.s.', 13, 2, 'pc'),
('Vena cava c.s.', 13, 2, 'pc'),
('Vermiform appendix, human sec.', 13, 2, 'pc'),
-- ── SLIDE / VARIOUS PREPARED ─────────────────────────────────
('Amoeba proteus, w.m.', 14, 3, 'pc'),
('Anthoceros sporophyte l.s.', 14, 4, 'pc'),
('Ascaris lumbricoides egg, w.m.', 14, 2, 'pc'),
('Chara w.m.', 14, 4, 'pc'),
('Chlamydomonas w.m.', 14, 2, 'pc'),
('Dicot and Monocot stem c.s.', 14, 5, 'pc'),
('Didinium devouring Paramecium w.m.', 14, 2, 'pc'),
('Dinoflagellates w.m.', 14, 4, 'pc'),
('Diplococcus pneumoniae (various)', 14, 3, 'pc'),
('Elodea root c.s.', 14, 2, 'pc'),
('Elodea w.m.', 14, 2, 'pc'),
('Entamoeba coli troph.', 14, 4, 'pc'),
('Equisetum strobilus l.s.', 14, 4, 'pc'),
('Fasciola hepatica egg w.m.', 14, 2, 'pc'),
('Fasciola hepatica w.m.', 14, 2, 'pc'),
('Fern c.s. of stem (rachis)', 14, 2, 'pc'),
('Fern Prothallium young sporophyte w.m.', 14, 2, 'pc'),
('Fern spores w.m.', 14, 2, 'pc'),
('Fern thallus w.m.', 14, 2, 'pc'),
('Germination pollen, w.m.', 14, 4, 'pc'),
('Giardia lamblia cyst', 14, 4, 'pc'),
('Giardia lamblia troph.', 14, 5, 'pc'),
('Grantia (Scypha) c.s.', 14, 2, 'pc'),
('Grantia (Scypha) l.s.', 14, 2, 'pc'),
('Grantia spicules w.m.', 14, 1, 'pc'),
('Hibiscus ovary l.s.', 14, 4, 'pc'),
('Hydra plain, c.s.', 14, 2, 'pc'),
('Lily ovary (gen. structure) c.s.', 14, 4, 'pc'),
('Lily pollen grains w.m.', 14, 4, 'pc'),
('Lycopodium strobilus, l.s.', 14, 4, 'pc'),
('Marchantia thallus with gemma cup c.s.', 14, 4, 'pc'),
('Mixed pollen grains w.m.', 14, 4, 'pc'),
('Mnium antheridia l.s.', 14, 4, 'pc'),
('Monocot and dicot leaf c.s.', 14, 5, 'pc'),
('Obelia w.m.', 14, 2, 'pc'),
('Onion root tip, l.s.', 14, 8, 'pc'),
('Pine female cone l.s.', 14, 3, 'pc'),
('Pine male cone, c.s.', 14, 3, 'pc'),
('Pine male cone, l.s.', 14, 3, 'pc'),
('Pine wood, radial section', 14, 3, 'pc'),
('Pinus leaf c.s.', 14, 3, 'pc'),
('Pinus young stem c.s.', 14, 3, 'pc'),
('Pinus wood c.s.', 14, 3, 'pc'),
('Planaria 3 regions c.s.', 14, 2, 'pc'),
('Planaria carbon-fed w.m.', 14, 4, 'pc'),
('Planaria plain, w.m.', 14, 4, 'pc'),
('Radiolaria, w.m.', 14, 3, 'pc'),
('Rhizopus w.m. with sporangia', 14, 3, 'pc'),
('Rhizopus w.m. with zygospores', 14, 3, 'pc'),
('Rotifers, w.m.', 14, 5, 'pc'),
('Sarcina lutea (various)', 14, 3, 'pc'),
('Schistosoma japonicum c.s. in liver', 14, 2, 'pc'),
('Selaginella strobilus, l.s.', 14, 4, 'pc'),
('Spirogyra w.m.', 14, 4, 'pc'),
('Taenia saginata egg, w.m.', 14, 3, 'pc'),
('Taenia saginata mature segment w.m.', 14, 5, 'pc'),
('Taenia saginata mature segment, w.m.', 14, 5, 'pc'),
('Taenia saginata scolex w.m.', 14, 5, 'pc'),
('Taenia solium egg, w.m.', 14, 3, 'pc'),
('Trichinella spiralis larva, w.m. (set 1)', 14, 2, 'pc'),
('Trichinella spiralis larva, w.m. (set 2)', 14, 2, 'pc'),
('Vorticella, w.m.', 14, 3, 'pc'),
-- ── EQUIPMENT / ANATOMICAL MODELS ────────────────────────────
('Circulatory system (Heart)', 2, 1, 'pc'),
('Digestive system', 2, 1, 'pc'),
('Endocrine System', 2, 1, 'pc'),
('Human full eye anatomy model', 2, 1, 'pc'),
('Integumentary (Skin) System', 2, 1, 'pc'),
('Nervous System (Brain and Spinal cord)', 2, 1, 'pc'),
('Reproductive System, Female Organ (set 1)', 2, 1, 'pc'),
('Reproductive System, Female Organ (set 2)', 2, 1, 'pc'),
('Reproductive System, Male organ (set 1)', 2, 1, 'pc'),
('Reproductive System, Male organ (set 2)', 2, 1, 'pc'),
('Respiratory system', 2, 1, 'pc'),
('Skeletal System', 2, 1, 'pc');

-- ── INVENTORY RECORDS (set available = total, location = Biology Lab) ─
INSERT INTO inventory_record (item_id, location_id, available_count)
SELECT item_id, 1, item_count FROM item;


-- ============================================================
--  SAMPLE QUERIES (commented for reference)
-- ============================================================

/*
-- 1. All items in Biology Lab with availability
SELECT * FROM v_inventory ORDER BY category, item_type, item_name;

-- 2. Filter by category
SELECT * FROM v_inventory WHERE category = 'Slide' ORDER BY item_type, item_name;

-- 3. Filter by type label (e.g., for a dropdown)
SELECT * FROM v_inventory WHERE item_type = 'Slide/Histology' ORDER BY item_name;

-- 4. Check what is available (not fully borrowed)
SELECT * FROM v_inventory WHERE available_count > 0 ORDER BY item_name;

-- 5. Search by name (for a search bar)
SELECT * FROM v_inventory WHERE item_name LIKE '%beaker%';

-- 6. Active borrows for a specific user
SELECT * FROM v_active_borrows WHERE user_name = 'Sample Student';

-- 7. Full audit log for an item
SELECT il.*, u.user_name FROM inventory_log il
JOIN user u ON u.user_id = il.user_id
WHERE il.item_id = 1 ORDER BY il.timestamp DESC;
*/
