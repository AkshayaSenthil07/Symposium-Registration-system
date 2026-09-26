-- =====================================================================
--  SYMPOSIUM MANAGEMENT SYSTEM  -  MySQL 8.0 schema
-- ---------------------------------------------------------------------
--  DBMS concepts demonstrated
--    * Normalised design (3NF) with lookup tables
--    * PRIMARY / FOREIGN / UNIQUE / CHECK / NOT NULL / DEFAULT constraints
--    * ON DELETE CASCADE / RESTRICT / SET NULL referential actions
--    * Secondary + composite indexes
--    * Views (multi-table joins, aggregation, correlated sub-queries)
--    * Stored function, stored procedures with TRANSACTIONS + SIGNAL
--    * BEFORE / AFTER triggers (business rules + audit trail)
--
--  Run with:  python setup_database.py     (recommended - also seeds data)
--        or:  mysql -u root -p < database/schema.sql   (schema only)
-- =====================================================================

DROP DATABASE IF EXISTS symposium_db;
CREATE DATABASE symposium_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE symposium_db;

-- ---------------------------------------------------------------------
-- 1. LOOKUP / MASTER TABLES
-- ---------------------------------------------------------------------
CREATE TABLE college (
    college_id    INT AUTO_INCREMENT PRIMARY KEY,
    college_name  VARCHAR(150) NOT NULL,
    city          VARCHAR(60),
    CONSTRAINT uq_college_name UNIQUE (college_name)
);

CREATE TABLE department (
    dept_id    INT AUTO_INCREMENT PRIMARY KEY,
    dept_name  VARCHAR(100) NOT NULL,
    CONSTRAINT uq_dept_name UNIQUE (dept_name)
);

CREATE TABLE venue (
    venue_id    INT AUTO_INCREMENT PRIMARY KEY,
    venue_name  VARCHAR(100) NOT NULL,
    location    VARCHAR(100),
    capacity    INT NOT NULL,
    CONSTRAINT uq_venue_name UNIQUE (venue_name),
    CONSTRAINT chk_venue_capacity CHECK (capacity > 0)
);

CREATE TABLE event_category (
    category_id    INT AUTO_INCREMENT PRIMARY KEY,
    category_name  VARCHAR(50) NOT NULL,
    CONSTRAINT uq_category_name UNIQUE (category_name)
);

-- Key/value store for symposium-wide settings (name, tagline, ...)
CREATE TABLE app_setting (
    setting_key    VARCHAR(50) PRIMARY KEY,
    setting_value  VARCHAR(255) NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. USERS  (login credentials for both admins and participants)
-- ---------------------------------------------------------------------
CREATE TABLE app_user (
    user_id          INT AUTO_INCREMENT PRIMARY KEY,
    full_name        VARCHAR(100) NOT NULL,
    email            VARCHAR(120) NOT NULL,
    phone            VARCHAR(15),
    password_hash    VARCHAR(255) NOT NULL,              -- PBKDF2-SHA256, never plain text
    role             ENUM('ADMIN','PARTICIPANT') NOT NULL DEFAULT 'PARTICIPANT',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    failed_attempts  TINYINT UNSIGNED NOT NULL DEFAULT 0,  -- brute-force protection
    locked_until     DATETIME NULL,
    last_login       DATETIME NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_email UNIQUE (email),
    CONSTRAINT chk_user_email CHECK (email LIKE '%_@_%._%'),
    CONSTRAINT chk_user_phone CHECK (phone IS NULL OR phone REGEXP '^[0-9]{10}$')
);

-- 1:1 extension of app_user for participants (keeps app_user free of NULL-heavy columns)
CREATE TABLE participant_profile (
    user_id        INT PRIMARY KEY,
    college_id     INT NOT NULL,
    dept_id        INT NOT NULL,
    year_of_study  TINYINT NOT NULL,
    gender         ENUM('Male','Female','Other'),
    CONSTRAINT fk_profile_user    FOREIGN KEY (user_id)    REFERENCES app_user(user_id)     ON DELETE CASCADE,
    CONSTRAINT fk_profile_college FOREIGN KEY (college_id) REFERENCES college(college_id)   ON DELETE RESTRICT,
    CONSTRAINT fk_profile_dept    FOREIGN KEY (dept_id)    REFERENCES department(dept_id)   ON DELETE RESTRICT,
    CONSTRAINT chk_profile_year   CHECK (year_of_study BETWEEN 1 AND 5)
);

-- ---------------------------------------------------------------------
-- 3. EVENTS
-- ---------------------------------------------------------------------
CREATE TABLE event (
    event_id           INT AUTO_INCREMENT PRIMARY KEY,
    event_name         VARCHAR(100) NOT NULL,
    category_id        INT NOT NULL,
    description        TEXT,
    venue_id           INT NULL,
    event_date         DATE NOT NULL,
    start_time         TIME NOT NULL,
    end_time           TIME NOT NULL,
    registration_fee   DECIMAL(8,2) NOT NULL DEFAULT 0,
    max_participants   INT NOT NULL,
    coordinator_name   VARCHAR(100),
    coordinator_phone  VARCHAR(15),
    status             ENUM('OPEN','CLOSED','COMPLETED','CANCELLED') NOT NULL DEFAULT 'OPEN',
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_event_name   UNIQUE (event_name),
    CONSTRAINT fk_event_cat    FOREIGN KEY (category_id) REFERENCES event_category(category_id) ON DELETE RESTRICT,
    CONSTRAINT fk_event_venue  FOREIGN KEY (venue_id)    REFERENCES venue(venue_id)             ON DELETE SET NULL,
    CONSTRAINT chk_event_fee   CHECK (registration_fee >= 0),
    CONSTRAINT chk_event_max   CHECK (max_participants > 0),
    CONSTRAINT chk_event_time  CHECK (end_time > start_time)
);

-- ---------------------------------------------------------------------
-- 4. TRANSACTIONS: REGISTRATION, PAYMENT, RESULTS
-- ---------------------------------------------------------------------
CREATE TABLE registration (
    reg_id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT NOT NULL,
    event_id       INT NOT NULL,
    team_name      VARCHAR(60),
    status         ENUM('PENDING','CONFIRMED','CANCELLED') NOT NULL DEFAULT 'PENDING',
    attended       BOOLEAN NOT NULL DEFAULT FALSE,
    registered_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reg_user_event UNIQUE (user_id, event_id),       -- no duplicate registrations
    CONSTRAINT fk_reg_user  FOREIGN KEY (user_id)  REFERENCES app_user(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_reg_event FOREIGN KEY (event_id) REFERENCES event(event_id)   ON DELETE CASCADE
);

CREATE TABLE payment (
    payment_id       INT AUTO_INCREMENT PRIMARY KEY,
    reg_id           INT NOT NULL,
    amount           DECIMAL(8,2) NOT NULL,
    method           ENUM('UPI','CARD','NET_BANKING','CASH','FREE') NOT NULL,
    transaction_ref  VARCHAR(40) NOT NULL,
    status           ENUM('PENDING','SUCCESS','FAILED','REFUNDED') NOT NULL DEFAULT 'PENDING',
    paid_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_payment_ref UNIQUE (transaction_ref),
    CONSTRAINT fk_payment_reg FOREIGN KEY (reg_id) REFERENCES registration(reg_id) ON DELETE CASCADE,
    CONSTRAINT chk_payment_amount CHECK (amount >= 0)
);

CREATE TABLE event_result (
    event_id  INT NOT NULL,
    position  TINYINT NOT NULL,
    reg_id    INT NOT NULL,
    PRIMARY KEY (event_id, position),                         -- composite key
    CONSTRAINT uq_result_reg   UNIQUE (reg_id),               -- one prize per registration
    CONSTRAINT fk_result_event FOREIGN KEY (event_id) REFERENCES event(event_id)       ON DELETE CASCADE,
    CONSTRAINT fk_result_reg   FOREIGN KEY (reg_id)   REFERENCES registration(reg_id)  ON DELETE CASCADE,
    CONSTRAINT chk_result_pos  CHECK (position BETWEEN 1 AND 3)
);

CREATE TABLE audit_log (
    log_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NULL,
    action      VARCHAR(50) NOT NULL,
    details     VARCHAR(255),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- 5. INDEXES  (speed up the most frequent look-ups / filters)
-- ---------------------------------------------------------------------
CREATE INDEX idx_event_date        ON event(event_date);
CREATE INDEX idx_event_status      ON event(status);
CREATE INDEX idx_reg_event_status  ON registration(event_id, status);
CREATE INDEX idx_payment_status    ON payment(status);
CREATE INDEX idx_audit_created     ON audit_log(created_at);
CREATE INDEX idx_user_role         ON app_user(role);

-- ---------------------------------------------------------------------
-- 6. STORED FUNCTION
-- ---------------------------------------------------------------------
DELIMITER $$

CREATE FUNCTION fn_seats_left(p_event_id INT) RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_capacity INT DEFAULT 0;
    DECLARE v_taken    INT DEFAULT 0;
    SELECT max_participants INTO v_capacity FROM event WHERE event_id = p_event_id;
    SELECT COUNT(*) INTO v_taken
      FROM registration
     WHERE event_id = p_event_id AND status <> 'CANCELLED';
    RETURN v_capacity - v_taken;
END$$

-- ---------------------------------------------------------------------
-- 7. TRIGGERS
-- ---------------------------------------------------------------------

-- Normalise e-mail addresses so logins are case-insensitive and unique
CREATE TRIGGER trg_user_before_insert
BEFORE INSERT ON app_user
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
END$$

CREATE TRIGGER trg_user_before_update
BEFORE UPDATE ON app_user
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
END$$

-- Business rule: cannot register for a closed / full event
CREATE TRIGGER trg_registration_before_insert
BEFORE INSERT ON registration
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);
    SELECT status INTO v_status FROM event WHERE event_id = NEW.event_id;
    -- unknown event: fall through and let the FOREIGN KEY reject the row
    IF v_status IS NOT NULL THEN
        IF v_status <> 'OPEN' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registrations are closed for this event.';
        END IF;
        IF fn_seats_left(NEW.event_id) <= 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Sorry, this event is already full.';
        END IF;
    END IF;
END$$

-- Successful payment automatically confirms the registration
CREATE TRIGGER trg_payment_after_insert
AFTER INSERT ON payment
FOR EACH ROW
BEGIN
    IF NEW.status = 'SUCCESS' THEN
        UPDATE registration SET status = 'CONFIRMED' WHERE reg_id = NEW.reg_id;
    END IF;
END$$

-- Payment verified later (cash) -> confirm;  refunded -> cancel registration
CREATE TRIGGER trg_payment_after_update
AFTER UPDATE ON payment
FOR EACH ROW
BEGIN
    IF NEW.status = 'SUCCESS' AND OLD.status <> 'SUCCESS' THEN
        UPDATE registration SET status = 'CONFIRMED' WHERE reg_id = NEW.reg_id;
    ELSEIF NEW.status = 'REFUNDED' AND OLD.status <> 'REFUNDED' THEN
        UPDATE registration SET status = 'CANCELLED' WHERE reg_id = NEW.reg_id;
    END IF;
END$$

-- Audit trail of every registration status / attendance change
CREATE TRIGGER trg_registration_after_update
AFTER UPDATE ON registration
FOR EACH ROW
BEGIN
    IF NEW.status <> OLD.status THEN
        INSERT INTO audit_log (user_id, action, details)
        VALUES (NEW.user_id, 'REG_STATUS',
                CONCAT('Reg #', NEW.reg_id, ' : ', OLD.status, ' -> ', NEW.status));
    END IF;
    IF NEW.attended <> OLD.attended THEN
        INSERT INTO audit_log (user_id, action, details)
        VALUES (NEW.user_id, 'ATTENDANCE',
                CONCAT('Reg #', NEW.reg_id, ' marked ', IF(NEW.attended, 'PRESENT', 'ABSENT')));
    END IF;
END$$

CREATE TRIGGER trg_event_after_delete
AFTER DELETE ON event
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, details)
    VALUES (NULL, 'EVENT_DELETED', CONCAT('Event #', OLD.event_id, ' "', OLD.event_name, '" deleted'));
END$$

-- ---------------------------------------------------------------------
-- 8. STORED PROCEDURES (with explicit TRANSACTION control)
-- ---------------------------------------------------------------------

-- Registers a participant for an event and records the payment atomically.
CREATE PROCEDURE sp_register_participant(
    IN  p_user_id   INT,
    IN  p_event_id  INT,
    IN  p_team_name VARCHAR(60),
    IN  p_method    VARCHAR(20),
    OUT p_reg_id    INT
)
BEGIN
    DECLARE v_fee        DECIMAL(8,2);
    DECLARE v_status     VARCHAR(20);
    DECLARE v_date       DATE;
    DECLARE v_start      TIME;
    DECLARE v_end        TIME;
    DECLARE v_clash      INT DEFAULT 0;
    DECLARE v_existing   INT DEFAULT NULL;
    DECLARE v_ex_status  VARCHAR(20) DEFAULT NULL;
    DECLARE v_ref        VARCHAR(40);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    IF NOT EXISTS (SELECT 1 FROM participant_profile pp JOIN app_user u ON u.user_id = pp.user_id
                    WHERE pp.user_id = p_user_id AND u.is_active) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only active participant accounts can register for events.';
    END IF;

    -- lock the event row so two people cannot grab the last seat simultaneously
    SELECT registration_fee, status, event_date, start_time, end_time
      INTO v_fee, v_status, v_date, v_start, v_end
      FROM event WHERE event_id = p_event_id
       FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Event not found.';
    END IF;
    IF v_status <> 'OPEN' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registrations are closed for this event.';
    END IF;
    IF v_date < CURDATE() THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This event has already taken place.';
    END IF;

    SELECT reg_id, status INTO v_existing, v_ex_status
      FROM registration
     WHERE user_id = p_user_id AND event_id = p_event_id
       FOR UPDATE;

    IF v_existing IS NOT NULL AND v_ex_status <> 'CANCELLED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'You are already registered for this event.';
    END IF;
    IF fn_seats_left(p_event_id) <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Sorry, this event is already full.';
    END IF;

    -- time-clash detection with the participant's other active registrations
    SELECT COUNT(*) INTO v_clash
      FROM registration r
      JOIN event e ON e.event_id = r.event_id
     WHERE r.user_id = p_user_id
       AND r.status <> 'CANCELLED'
       AND e.event_id <> p_event_id
       AND e.event_date = v_date
       AND e.start_time < v_end
       AND e.end_time   > v_start;
    IF v_clash > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Time clash: you are registered for another event in this slot.';
    END IF;

    IF v_existing IS NULL THEN
        INSERT INTO registration (user_id, event_id, team_name, status)
        VALUES (p_user_id, p_event_id, NULLIF(TRIM(p_team_name), ''), 'PENDING');
        SET p_reg_id = LAST_INSERT_ID();
    ELSE
        UPDATE registration
           SET status = 'PENDING', team_name = NULLIF(TRIM(p_team_name), ''),
               attended = FALSE, registered_at = CURRENT_TIMESTAMP
         WHERE reg_id = v_existing;
        SET p_reg_id = v_existing;
    END IF;

    SET v_ref = CONCAT('TXN', DATE_FORMAT(NOW(), '%y%m%d'),
                       UPPER(SUBSTRING(REPLACE(UUID(), '-', ''), 1, 10)));

    IF v_fee = 0 THEN
        INSERT INTO payment (reg_id, amount, method, transaction_ref, status)
        VALUES (p_reg_id, 0, 'FREE', v_ref, 'SUCCESS');
    ELSEIF p_method = 'CASH' THEN
        INSERT INTO payment (reg_id, amount, method, transaction_ref, status)
        VALUES (p_reg_id, v_fee, 'CASH', v_ref, 'PENDING');
    ELSE
        INSERT INTO payment (reg_id, amount, method, transaction_ref, status)
        VALUES (p_reg_id, v_fee, p_method, v_ref, 'SUCCESS');
    END IF;

    INSERT INTO audit_log (user_id, action, details)
    VALUES (p_user_id, 'REGISTER', CONCAT('Registered for event #', p_event_id, ' (reg #', p_reg_id, ')'));

    COMMIT;
END$$

-- Cancels a registration; successful payments are refunded (trigger cancels the registration)
CREATE PROCEDURE sp_cancel_registration(IN p_reg_id INT, IN p_actor_id INT)
BEGIN
    DECLARE v_status   VARCHAR(20);
    DECLARE v_attended BOOLEAN;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT status, attended INTO v_status, v_attended
      FROM registration WHERE reg_id = p_reg_id FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registration not found.';
    END IF;
    IF v_status = 'CANCELLED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registration is already cancelled.';
    END IF;
    IF v_attended THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot cancel - attendance already recorded.';
    END IF;

    UPDATE payment SET status = 'REFUNDED' WHERE reg_id = p_reg_id AND status = 'SUCCESS';
    UPDATE payment SET status = 'FAILED'   WHERE reg_id = p_reg_id AND status = 'PENDING';
    UPDATE registration SET status = 'CANCELLED' WHERE reg_id = p_reg_id;
    DELETE FROM event_result WHERE reg_id = p_reg_id;

    INSERT INTO audit_log (user_id, action, details)
    VALUES (p_actor_id, 'CANCEL', CONCAT('Cancelled reg #', p_reg_id));

    COMMIT;
END$$

DELIMITER ;

-- ---------------------------------------------------------------------
-- 9. VIEWS
-- ---------------------------------------------------------------------

-- Latest payment per registration (correlated sub-query)
CREATE VIEW v_latest_payment AS
SELECT p.*
  FROM payment p
 WHERE p.payment_id = (SELECT MAX(p2.payment_id) FROM payment p2 WHERE p2.reg_id = p.reg_id);

-- One row per event with live statistics
CREATE VIEW v_event_summary AS
SELECT e.event_id, e.event_name, c.category_name, e.category_id,
       v.venue_name, e.venue_id, e.event_date, e.start_time, e.end_time,
       e.registration_fee, e.max_participants, e.status, e.description,
       e.coordinator_name, e.coordinator_phone,
       COUNT(CASE WHEN r.status <> 'CANCELLED' THEN 1 END)          AS registered,
       COUNT(CASE WHEN r.status = 'CONFIRMED' THEN 1 END)           AS confirmed,
       COUNT(CASE WHEN r.attended AND r.status <> 'CANCELLED' THEN 1 END) AS attended,
       e.max_participants - COUNT(CASE WHEN r.status <> 'CANCELLED' THEN 1 END) AS seats_left,
       COALESCE(SUM(CASE WHEN lp.status = 'SUCCESS' THEN lp.amount END), 0) AS revenue
  FROM event e
  JOIN event_category c    ON c.category_id = e.category_id
  LEFT JOIN venue v        ON v.venue_id = e.venue_id
  LEFT JOIN registration r ON r.event_id = e.event_id
  LEFT JOIN v_latest_payment lp ON lp.reg_id = r.reg_id
 GROUP BY e.event_id;

-- Participant details (joins user + profile + college + department)
CREATE VIEW v_participant_details AS
SELECT u.user_id, u.full_name, u.email, u.phone, u.is_active, u.created_at, u.last_login,
       c.college_name, d.dept_name, pp.year_of_study, pp.gender,
       pp.college_id, pp.dept_id,
       (SELECT COUNT(*) FROM registration r
         WHERE r.user_id = u.user_id AND r.status <> 'CANCELLED') AS active_registrations
  FROM app_user u
  JOIN participant_profile pp ON pp.user_id = u.user_id
  JOIN college c    ON c.college_id = pp.college_id
  JOIN department d ON d.dept_id = pp.dept_id
 WHERE u.role = 'PARTICIPANT';

-- Complete registration information used by admin screens & exports
CREATE VIEW v_registration_details AS
SELECT r.reg_id, r.user_id, r.event_id, r.team_name, r.status, r.attended, r.registered_at,
       u.full_name, u.email, u.phone,
       c.college_name, d.dept_name, pp.year_of_study,
       e.event_name, e.event_date, e.start_time, e.end_time, e.registration_fee,
       cat.category_name, v.venue_name,
       lp.payment_id, lp.method AS payment_method, lp.amount, lp.status AS payment_status,
       lp.transaction_ref, lp.paid_at,
       er.position AS result_position
  FROM registration r
  JOIN app_user u               ON u.user_id = r.user_id
  LEFT JOIN participant_profile pp ON pp.user_id = u.user_id
  LEFT JOIN college c           ON c.college_id = pp.college_id
  LEFT JOIN department d        ON d.dept_id = pp.dept_id
  JOIN event e                  ON e.event_id = r.event_id
  JOIN event_category cat       ON cat.category_id = e.category_id
  LEFT JOIN venue v             ON v.venue_id = e.venue_id
  LEFT JOIN v_latest_payment lp ON lp.reg_id = r.reg_id
  LEFT JOIN event_result er     ON er.reg_id = r.reg_id;

-- College leaderboard (participation + podium finishes)
CREATE VIEW v_college_leaderboard AS
SELECT c.college_id, c.college_name,
       COUNT(DISTINCT pp.user_id) AS participants,
       COUNT(DISTINCT CASE WHEN r.status <> 'CANCELLED' THEN r.reg_id END) AS registrations,
       COUNT(DISTINCT CASE WHEN er.position = 1 THEN er.reg_id END) AS gold,
       COUNT(DISTINCT CASE WHEN er.position = 2 THEN er.reg_id END) AS silver,
       COUNT(DISTINCT CASE WHEN er.position = 3 THEN er.reg_id END) AS bronze,
       COUNT(DISTINCT CASE WHEN er.position = 1 THEN er.reg_id END) * 5
     + COUNT(DISTINCT CASE WHEN er.position = 2 THEN er.reg_id END) * 3
     + COUNT(DISTINCT CASE WHEN er.position = 3 THEN er.reg_id END) * 1 AS points
  FROM college c
  LEFT JOIN participant_profile pp ON pp.college_id = c.college_id
  LEFT JOIN registration r         ON r.user_id = pp.user_id
  LEFT JOIN event_result er        ON er.reg_id = r.reg_id
 GROUP BY c.college_id, c.college_name;
