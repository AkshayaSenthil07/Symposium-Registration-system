-- =====================================================================
--  Demo queries for evaluation / viva  (run after setup_database.py)
--  Most of these can also be run from the app: Admin -> SQL Console
-- =====================================================================
USE symposium_db;

-- 1. INNER JOIN across 4 tables: who registered for what
SELECT u.full_name, c.college_name, e.event_name, r.status
  FROM registration r
  JOIN app_user u            ON u.user_id = r.user_id
  JOIN participant_profile p ON p.user_id = u.user_id
  JOIN college c             ON c.college_id = p.college_id
  JOIN event e               ON e.event_id = r.event_id
 ORDER BY e.event_name, u.full_name;

-- 2. LEFT JOIN + GROUP BY: every event with its registration count (including zero)
SELECT e.event_name, COUNT(r.reg_id) AS registrations
  FROM event e
  LEFT JOIN registration r ON r.event_id = e.event_id AND r.status <> 'CANCELLED'
 GROUP BY e.event_id, e.event_name
 ORDER BY registrations DESC;

-- 3. GROUP BY ... HAVING: participants registered for 3 or more events
SELECT u.full_name, COUNT(*) AS events
  FROM registration r JOIN app_user u ON u.user_id = r.user_id
 WHERE r.status <> 'CANCELLED'
 GROUP BY u.user_id, u.full_name
HAVING COUNT(*) >= 3;

-- 4. Sub-query: events with above-average registrations
SELECT event_name, registered
  FROM v_event_summary
 WHERE registered > (SELECT AVG(registered) FROM v_event_summary);

-- 5. Correlated sub-query: each participant's most expensive event
SELECT u.full_name, e.event_name, e.registration_fee
  FROM registration r
  JOIN app_user u ON u.user_id = r.user_id
  JOIN event e    ON e.event_id = r.event_id
 WHERE e.registration_fee = (SELECT MAX(e2.registration_fee)
                               FROM registration r2 JOIN event e2 ON e2.event_id = r2.event_id
                              WHERE r2.user_id = r.user_id);

-- 6. Views
SELECT * FROM v_event_summary;
SELECT * FROM v_college_leaderboard ORDER BY points DESC;

-- 7. Stored function
SELECT event_name, max_participants, fn_seats_left(event_id) AS seats_left FROM event;

-- 8. Stored procedure with transaction (register user 3 for event 7, pay via UPI)
CALL sp_register_participant(3, 7, NULL, 'UPI', @reg_id);
SELECT @reg_id AS new_registration;
SELECT * FROM v_registration_details WHERE reg_id = @reg_id;   -- status is CONFIRMED (trigger!)

-- 9. Trigger demo: a SIGNAL from the procedure / trigger rolls everything back
CALL sp_register_participant(3, 7, NULL, 'UPI', @reg_id);       -- ERROR: already registered

-- 10. Cancel -> payment REFUNDED -> trigger cancels registration -> audit_log rows
CALL sp_cancel_registration(@reg_id, 3);
SELECT * FROM audit_log ORDER BY log_id DESC LIMIT 5;

-- 11. Constraint demos (each of these fails on purpose)
INSERT INTO venue (venue_name, capacity) VALUES ('Bad Hall', 0);             -- CHECK
INSERT INTO app_user (full_name, email, password_hash) VALUES ('X', 'not-an-email', 'x');  -- CHECK
INSERT INTO registration (user_id, event_id) VALUES (3, 9999);               -- FOREIGN KEY
DELETE FROM college WHERE college_id = 1;                                    -- FK RESTRICT

-- 12. Index usage
EXPLAIN SELECT * FROM event WHERE event_date >= CURDATE();
SHOW INDEX FROM registration;

-- 13. Metadata: triggers, routines
SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION, EVENT_OBJECT_TABLE
  FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE();
SELECT ROUTINE_NAME, ROUTINE_TYPE FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = DATABASE();
