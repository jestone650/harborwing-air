-- =====================================================================
--  HarborWing Air - Reservation Database (MySQL 8.0.16 or newer)
--  File: database/schema.sql
--
--  Running this file RESETS the database: it drops and recreates
--  `harborwing` with every table, key, constraint and index.
--
--  Conventions
--    * Every date/time column stores UTC (columns end in _utc).
--    * All tables use InnoDB (foreign keys + transactions).
--    * Small code lists (status, ticket type, travel class) are enforced
--      with CHECK constraints.  Airlines and aircraft types are real
--      supporting tables.
--
--  Deletion rules (documented policy)
--    * Parent rows that are still used CANNOT be deleted (RESTRICT):
--      passengers with reservations, airports used by schedules/legs,
--      schedules with legs or costs, legs/payments still linked to a
--      reservation, airlines/aircraft types/calendar dates in use.
--    * Deleting a booking agent keeps the reservations and sets their
--      agent to NULL (they become "direct" reservations).
--    * Deleting a reservation deletes only its LINK rows in
--      reservation_payment / reservation_leg (CASCADE).  The payments
--      and legs themselves are never deleted.
-- =====================================================================

DROP DATABASE IF EXISTS harborwing;
CREATE DATABASE harborwing CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE harborwing;

-- ---------------------------------------------------------------------
-- Supporting reference tables
-- ---------------------------------------------------------------------
CREATE TABLE airline (
    airline_code    CHAR(2)      NOT NULL,
    airline_name    VARCHAR(100) NOT NULL,
    is_demo_data    BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT pk_airline PRIMARY KEY (airline_code),
    CONSTRAINT uq_airline_name UNIQUE (airline_name),
    CONSTRAINT ck_airline_code CHECK (REGEXP_LIKE(airline_code, '^[A-Z0-9]{2}$', 'c'))
) ENGINE = InnoDB;

CREATE TABLE aircraft_type (
    aircraft_type_code  VARCHAR(10)  NOT NULL,
    aircraft_description VARCHAR(100) NOT NULL,
    seat_capacity       SMALLINT UNSIGNED NOT NULL,
    is_demo_data        BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT pk_aircraft_type PRIMARY KEY (aircraft_type_code),
    CONSTRAINT ck_aircraft_seats CHECK (seat_capacity BETWEEN 1 AND 900)
) ENGINE = InnoDB;

CREATE TABLE calendar_date (
    day_date        DATE     NOT NULL,
    day_of_month    TINYINT UNSIGNED NOT NULL,
    is_business_day BOOLEAN  NOT NULL,
    CONSTRAINT pk_calendar_date PRIMARY KEY (day_date),
    CONSTRAINT ck_calendar_dom CHECK (day_of_month BETWEEN 1 AND 31)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- People
-- ---------------------------------------------------------------------
CREATE TABLE booking_agent (
    agent_id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    agent_name      VARCHAR(120) NOT NULL,
    agent_details   VARCHAR(500) NULL,
    CONSTRAINT pk_booking_agent PRIMARY KEY (agent_id)
) ENGINE = InnoDB;

CREATE TABLE passenger (
    passenger_id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name            VARCHAR(60)  NOT NULL,
    second_name           VARCHAR(60)  NULL,
    last_name             VARCHAR(60)  NOT NULL,
    phone_number          VARCHAR(30)  NOT NULL,
    email_address         VARCHAR(120) NOT NULL,
    address_line_1        VARCHAR(120) NOT NULL,
    address_line_2        VARCHAR(120) NULL,
    city                  VARCHAR(80)  NOT NULL,
    state_province_county VARCHAR(80)  NULL,
    country               VARCHAR(80)  NOT NULL,
    other_details         VARCHAR(500) NULL,
    CONSTRAINT pk_passenger PRIMARY KEY (passenger_id),
    CONSTRAINT uq_passenger_email UNIQUE (email_address),
    CONSTRAINT ck_passenger_email CHECK (email_address LIKE '%_@_%._%')
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- Airports and flights
-- ---------------------------------------------------------------------
CREATE TABLE airport (
    airport_code      CHAR(3)      NOT NULL,
    airport_name      VARCHAR(120) NOT NULL,
    airport_location  VARCHAR(160) NOT NULL,
    other_details     VARCHAR(500) NULL,
    CONSTRAINT pk_airport PRIMARY KEY (airport_code),
    CONSTRAINT uq_airport_name UNIQUE (airport_name),
    CONSTRAINT ck_airport_code CHECK (REGEXP_LIKE(airport_code, '^[A-Z]{3}$', 'c'))
) ENGINE = InnoDB;

-- Simplifying assumption: flight_number alone identifies a schedule.
CREATE TABLE flight_schedule (
    flight_number             VARCHAR(10)  NOT NULL,
    airline_code              CHAR(2)      NOT NULL,
    usual_aircraft_type_code  VARCHAR(10)  NOT NULL,
    origin_airport_code       CHAR(3)      NOT NULL,
    destination_airport_code  CHAR(3)      NOT NULL,
    departure_datetime_utc    DATETIME     NOT NULL,
    arrival_datetime_utc      DATETIME     NOT NULL,
    CONSTRAINT pk_flight_schedule PRIMARY KEY (flight_number),
    CONSTRAINT fk_schedule_airline FOREIGN KEY (airline_code)
        REFERENCES airline (airline_code) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_schedule_aircraft FOREIGN KEY (usual_aircraft_type_code)
        REFERENCES aircraft_type (aircraft_type_code) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_schedule_origin FOREIGN KEY (origin_airport_code)
        REFERENCES airport (airport_code) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_schedule_destination FOREIGN KEY (destination_airport_code)
        REFERENCES airport (airport_code) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_schedule_airports CHECK (origin_airport_code <> destination_airport_code),
    CONSTRAINT ck_schedule_times CHECK (arrival_datetime_utc > departure_datetime_utc)
) ENGINE = InnoDB;

CREATE INDEX ix_schedule_route ON flight_schedule (origin_airport_code, destination_airport_code);
CREATE INDEX ix_schedule_departure ON flight_schedule (departure_datetime_utc);

-- One operated flight. Actual times stay NULL until the flight operates.
CREATE TABLE flight_leg (
    leg_id                    INT UNSIGNED NOT NULL AUTO_INCREMENT,
    flight_number             VARCHAR(10)  NOT NULL,
    origin_airport_code       CHAR(3)      NOT NULL,
    destination_airport_code  CHAR(3)      NOT NULL,
    actual_departure_utc      DATETIME     NULL,
    actual_arrival_utc        DATETIME     NULL,
    CONSTRAINT pk_flight_leg PRIMARY KEY (leg_id),
    CONSTRAINT fk_leg_schedule FOREIGN KEY (flight_number)
        REFERENCES flight_schedule (flight_number) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_leg_origin FOREIGN KEY (origin_airport_code)
        REFERENCES airport (airport_code) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_leg_destination FOREIGN KEY (destination_airport_code)
        REFERENCES airport (airport_code) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_leg_airports CHECK (origin_airport_code <> destination_airport_code),
    CONSTRAINT ck_leg_times CHECK (
        actual_departure_utc IS NULL OR actual_arrival_utc IS NULL
        OR actual_arrival_utc > actual_departure_utc),
    CONSTRAINT ck_leg_arrival_needs_departure CHECK (
        actual_arrival_utc IS NULL OR actual_departure_utc IS NOT NULL)
) ENGINE = InnoDB;

CREATE INDEX ix_leg_departure ON flight_leg (actual_departure_utc);

-- Cost history: a new row per validity period, old costs are kept.
CREATE TABLE flight_cost (
    flight_number       VARCHAR(10)   NOT NULL,
    aircraft_type_code  VARCHAR(10)   NOT NULL,
    valid_from_date     DATE          NOT NULL,
    valid_to_date       DATE          NOT NULL,
    cost_amount         DECIMAL(12,2) NOT NULL,
    CONSTRAINT pk_flight_cost PRIMARY KEY (flight_number, aircraft_type_code, valid_from_date),
    CONSTRAINT fk_cost_schedule FOREIGN KEY (flight_number)
        REFERENCES flight_schedule (flight_number) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_cost_aircraft FOREIGN KEY (aircraft_type_code)
        REFERENCES aircraft_type (aircraft_type_code) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_cost_valid_from FOREIGN KEY (valid_from_date)
        REFERENCES calendar_date (day_date) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_cost_valid_to FOREIGN KEY (valid_to_date)
        REFERENCES calendar_date (day_date) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_cost_dates CHECK (valid_to_date >= valid_from_date),
    CONSTRAINT ck_cost_amount CHECK (cost_amount >= 0)
) ENGINE = InnoDB;

CREATE INDEX ix_cost_aircraft ON flight_cost (aircraft_type_code);
CREATE INDEX ix_cost_valid_to ON flight_cost (valid_to_date);

-- ---------------------------------------------------------------------
-- Reservations and payments
-- ---------------------------------------------------------------------
CREATE TABLE reservation (
    reservation_id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    passenger_id            INT UNSIGNED NOT NULL,
    agent_id                INT UNSIGNED NULL,
    reservation_status_code VARCHAR(4)   NOT NULL,
    ticket_type_code        VARCHAR(6)   NOT NULL,
    travel_class_code       VARCHAR(5)   NOT NULL,
    created_at_utc          DATETIME     NOT NULL DEFAULT (UTC_TIMESTAMP()),
    number_in_party         SMALLINT UNSIGNED NOT NULL,
    CONSTRAINT pk_reservation PRIMARY KEY (reservation_id),
    CONSTRAINT fk_reservation_passenger FOREIGN KEY (passenger_id)
        REFERENCES passenger (passenger_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_reservation_agent FOREIGN KEY (agent_id)
        REFERENCES booking_agent (agent_id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT ck_reservation_status CHECK (reservation_status_code IN ('PEND','CONF','CANC','COMP')),
    CONSTRAINT ck_reservation_ticket CHECK (ticket_type_code IN ('ONEWAY','RETURN','MULTI')),
    CONSTRAINT ck_reservation_class CHECK (travel_class_code IN ('ECON','PREM','BUS','FIRST')),
    CONSTRAINT ck_reservation_party CHECK (number_in_party > 0)
) ENGINE = InnoDB;

CREATE INDEX ix_reservation_created ON reservation (created_at_utc);
CREATE INDEX ix_reservation_status ON reservation (reservation_status_code);

CREATE TABLE payment (
    payment_id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    payment_status_code VARCHAR(4)    NOT NULL,
    payment_date        DATE          NOT NULL,
    payment_amount      DECIMAL(12,2) NOT NULL,
    CONSTRAINT pk_payment PRIMARY KEY (payment_id),
    CONSTRAINT ck_payment_status CHECK (payment_status_code IN ('PEND','PAID','REFD','FAIL')),
    CONSTRAINT ck_payment_amount CHECK (payment_amount > 0)
) ENGINE = InnoDB;

CREATE INDEX ix_payment_date ON payment (payment_date);

-- ---------------------------------------------------------------------
-- Linking tables (many-to-many).  Composite PK = no duplicate pairs.
-- No allocation amount is stored here (business rule).
-- ---------------------------------------------------------------------
CREATE TABLE reservation_payment (
    reservation_id  INT UNSIGNED NOT NULL,
    payment_id      INT UNSIGNED NOT NULL,
    CONSTRAINT pk_reservation_payment PRIMARY KEY (reservation_id, payment_id),
    CONSTRAINT fk_rp_reservation FOREIGN KEY (reservation_id)
        REFERENCES reservation (reservation_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_rp_payment FOREIGN KEY (payment_id)
        REFERENCES payment (payment_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE INDEX ix_rp_payment ON reservation_payment (payment_id);

CREATE TABLE reservation_leg (
    reservation_id  INT UNSIGNED NOT NULL,
    leg_id          INT UNSIGNED NOT NULL,
    CONSTRAINT pk_reservation_leg PRIMARY KEY (reservation_id, leg_id),
    CONSTRAINT fk_rl_reservation FOREIGN KEY (reservation_id)
        REFERENCES reservation (reservation_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_rl_leg FOREIGN KEY (leg_id)
        REFERENCES flight_leg (leg_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE INDEX ix_rl_leg ON reservation_leg (leg_id);
