-- Row count of every table (each must be >= 50)
USE harborwing;

SELECT 'airline'             AS table_name, COUNT(*) AS row_count FROM airline
UNION ALL SELECT 'aircraft_type',        COUNT(*) FROM aircraft_type
UNION ALL SELECT 'calendar_date',        COUNT(*) FROM calendar_date
UNION ALL SELECT 'airport',              COUNT(*) FROM airport
UNION ALL SELECT 'booking_agent',        COUNT(*) FROM booking_agent
UNION ALL SELECT 'passenger',            COUNT(*) FROM passenger
UNION ALL SELECT 'flight_schedule',      COUNT(*) FROM flight_schedule
UNION ALL SELECT 'flight_leg',           COUNT(*) FROM flight_leg
UNION ALL SELECT 'flight_cost',          COUNT(*) FROM flight_cost
UNION ALL SELECT 'reservation',          COUNT(*) FROM reservation
UNION ALL SELECT 'payment',              COUNT(*) FROM payment
UNION ALL SELECT 'reservation_payment',  COUNT(*) FROM reservation_payment
UNION ALL SELECT 'reservation_leg',      COUNT(*) FROM reservation_leg;
