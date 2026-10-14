-- =====================================================================
-- HarborWing Air - example queries
-- Change the values in the SET lines to try other records.
-- =====================================================================
USE harborwing;

SET @reservation_id = 1;
SET @leg_id         = 1;

-- ---------------------------------------------------------------------
-- 1. View a reservation with its passenger, agent, payments and legs.
--
--    Why subqueries?  If we JOIN payments AND legs in one query, a
--    reservation with 2 payments and 3 legs returns 2 x 3 = 6 rows,
--    and SUM(payment_amount) would count each payment 3 times.
--    Aggregating each child table separately avoids that inflation.
-- ---------------------------------------------------------------------
SELECT r.reservation_id,
       r.reservation_status_code, r.ticket_type_code, r.travel_class_code,
       r.created_at_utc, r.number_in_party,
       CONCAT_WS(' ', p.first_name, p.second_name, p.last_name) AS main_passenger,
       p.email_address,
       COALESCE(a.agent_name, '(direct booking)')              AS booking_agent,
       COALESCE(pay.payment_count, 0)                           AS payment_count,
       COALESCE(pay.payment_total, 0.00)                        AS payment_total,
       COALESCE(leg.leg_count, 0)                               AS leg_count,
       leg.itinerary
FROM reservation r
JOIN passenger p             ON p.passenger_id = r.passenger_id
LEFT JOIN booking_agent a    ON a.agent_id = r.agent_id
LEFT JOIN (SELECT rp.reservation_id,
                  COUNT(*)              AS payment_count,
                  SUM(pm.payment_amount) AS payment_total
           FROM reservation_payment rp
           JOIN payment pm ON pm.payment_id = rp.payment_id
           GROUP BY rp.reservation_id) pay ON pay.reservation_id = r.reservation_id
LEFT JOIN (SELECT rl.reservation_id,
                  COUNT(*) AS leg_count,
                  GROUP_CONCAT(CONCAT(fl.flight_number, ' ', fl.origin_airport_code, '->',
                               fl.destination_airport_code)
                               ORDER BY fl.actual_departure_utc SEPARATOR ' | ') AS itinerary
           FROM reservation_leg rl
           JOIN flight_leg fl ON fl.leg_id = rl.leg_id
           GROUP BY rl.reservation_id) leg ON leg.reservation_id = r.reservation_id
WHERE r.reservation_id = @reservation_id;

-- 1b. Leg details for the same reservation (one row per leg)
SELECT fl.leg_id, fl.flight_number, fs.airline_code,
       fl.origin_airport_code, fl.destination_airport_code,
       fs.departure_datetime_utc AS scheduled_departure_utc,
       fl.actual_departure_utc, fl.actual_arrival_utc
FROM reservation_leg rl
JOIN flight_leg fl      ON fl.leg_id = rl.leg_id
JOIN flight_schedule fs ON fs.flight_number = fl.flight_number
WHERE rl.reservation_id = @reservation_id
ORDER BY fl.actual_departure_utc;

-- ---------------------------------------------------------------------
-- 2. Find reservations using a particular leg
-- ---------------------------------------------------------------------
SELECT r.reservation_id, r.reservation_status_code, r.number_in_party,
       CONCAT(p.first_name, ' ', p.last_name) AS main_passenger
FROM reservation_leg rl
JOIN reservation r ON r.reservation_id = rl.reservation_id
JOIN passenger p   ON p.passenger_id = r.passenger_id
WHERE rl.leg_id = @leg_id
ORDER BY r.reservation_id;

-- ---------------------------------------------------------------------
-- 3. Find payments linked to a reservation
--    shared_with_n_reservations > 1 means the payment also covers
--    other reservations (the exact split is NOT stored - see README).
-- ---------------------------------------------------------------------
SELECT pm.payment_id, pm.payment_status_code, pm.payment_date, pm.payment_amount,
       (SELECT COUNT(*) FROM reservation_payment x
        WHERE x.payment_id = pm.payment_id) AS shared_with_n_reservations
FROM reservation_payment rp
JOIN payment pm ON pm.payment_id = rp.payment_id
WHERE rp.reservation_id = @reservation_id
ORDER BY pm.payment_date;

-- ---------------------------------------------------------------------
-- 4. Find the flight cost for a flight, aircraft type and date.
--    Overlap policy: if periods ever overlap, the period that started
--    most recently wins (ORDER BY valid_from_date DESC LIMIT 1).
--    The seed script and the app also prevent overlaps.
-- ---------------------------------------------------------------------
SELECT flight_number, aircraft_type_code, valid_from_date, valid_to_date
INTO @flight, @aircraft, @from_date, @to_date
FROM flight_cost LIMIT 1;                     -- picks an existing record for the demo

SET @on_date = @from_date + INTERVAL 10 DAY;  -- any date you want to price

SELECT fc.flight_number, fc.aircraft_type_code, fc.valid_from_date, fc.valid_to_date,
       fc.cost_amount
FROM flight_cost fc
WHERE fc.flight_number      = @flight
  AND fc.aircraft_type_code = @aircraft
  AND @on_date BETWEEN fc.valid_from_date AND fc.valid_to_date
ORDER BY fc.valid_from_date DESC
LIMIT 1;

-- ---------------------------------------------------------------------
-- Extra evidence queries (useful for the video)
-- ---------------------------------------------------------------------
-- Reservations with several payments AND several legs
SELECT r.reservation_id,
       (SELECT COUNT(*) FROM reservation_payment x WHERE x.reservation_id = r.reservation_id) AS payments,
       (SELECT COUNT(*) FROM reservation_leg y     WHERE y.reservation_id = r.reservation_id) AS legs
FROM reservation r
HAVING payments > 1 AND legs > 1
LIMIT 10;

-- Payments shared by several reservations
SELECT payment_id, COUNT(*) AS reservations_covered
FROM reservation_payment
GROUP BY payment_id
HAVING COUNT(*) > 1
LIMIT 10;

-- Direct vs agent-assisted reservations
SELECT IF(agent_id IS NULL, 'direct', 'agent-assisted') AS channel, COUNT(*) AS reservations
FROM reservation GROUP BY channel;

-- A flight with several cost validity periods
SELECT flight_number, aircraft_type_code, valid_from_date, valid_to_date, cost_amount
FROM flight_cost
WHERE (flight_number, aircraft_type_code) IN (
      SELECT flight_number, aircraft_type_code FROM flight_cost
      GROUP BY flight_number, aircraft_type_code HAVING COUNT(*) > 1)
ORDER BY flight_number, aircraft_type_code, valid_from_date
LIMIT 12;
