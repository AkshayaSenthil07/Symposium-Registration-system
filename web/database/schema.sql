-- =====================================================================
--  SYMPOSIUM WEBSITE  -  MySQL 8.0 schema  (live version)
-- ---------------------------------------------------------------------
--  Created by:  python manage.py init-db
--  (the script also creates two limited MySQL users - the website never
--   connects as root)
--
--  DBMS concepts: 3NF design, PK/FK/UNIQUE/CHECK constraints, referential
--  actions, indexes, views, stored function, stored procedures with
--  transactions, triggers, column-level privileges (see manage.py).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. MASTER DATA
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
    location    VARCHAR(150),
    capacity    INT NOT NULL,
    CONSTRAINT uq_venue_name UNIQUE (venue_name),
    CONSTRAINT chk_venue_capacity CHECK (capacity > 0)
);

CREATE TABLE event_category (
    category_id    INT AUTO_INCREMENT PRIMARY KEY,
    category_name  VARCHAR(50) NOT NULL,
    CONSTRAINT uq_category_name UNIQUE (category_name)
);

-- symposium-wide settings editable from Admin > Settings (no secrets here)
CREATE TABLE app_setting (
    setting_key    VARCHAR(60) PRIMARY KEY,
    setting_value  TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. USERS
-- ---------------------------------------------------------------------
CREATE TABLE app_user (
    user_id               INT AUTO_INCREMENT PRIMARY KEY,
    full_name             VARCHAR(100) NOT NULL,
    email                 VARCHAR(120) NOT NULL,
    phone                 VARCHAR(15),
    password_hash         VARCHAR(255) NOT NULL,
    role                  ENUM('ADMIN','CASHIER','COORDINATOR','PARTICIPANT') NOT NULL DEFAULT 'PARTICIPANT',
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified        BOOLEAN NOT NULL DEFAULT FALSE,
    must_change_password  BOOLEAN NOT NULL DEFAULT FALSE,
    failed_attempts       TINYINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until          DATETIME NULL,
    last_login            DATETIME NULL,
    is_demo               BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_email UNIQUE (email),
    CONSTRAINT chk_user_email CHECK (email LIKE '%_@_%._%'),
    CONSTRAINT chk_user_phone CHECK (phone IS NULL OR phone REGEXP '^[0-9]{10}$')
);

CREATE TABLE participant_profile (
    user_id        INT PRIMARY KEY,
    college_id     INT NOT NULL,
    dept_id        INT NOT NULL,
    year_of_study  TINYINT NOT NULL,
    gender         ENUM('Male','Female','Other'),
    CONSTRAINT fk_profile_user    FOREIGN KEY (user_id)    REFERENCES app_user(user_id)   ON DELETE CASCADE,
    CONSTRAINT fk_profile_college FOREIGN KEY (college_id) REFERENCES college(college_id) ON DELETE RESTRICT,
    CONSTRAINT fk_profile_dept    FOREIGN KEY (dept_id)    REFERENCES department(dept_id) ON DELETE RESTRICT,
    CONSTRAINT chk_profile_year   CHECK (year_of_study BETWEEN 1 AND 5)
);

-- one-time tokens for e-mail verification and password reset (only a SHA-256 hash is stored)
CREATE TABLE user_token (
    token_id    INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    purpose     ENUM('VERIFY','RESET') NOT NULL,
    token_hash  CHAR(64) NOT NULL,
    expires_at  DATETIME NOT NULL,
    used_at     DATETIME NULL,
    CONSTRAINT uq_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_token_user FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 3. EVENTS
-- ---------------------------------------------------------------------
CREATE TABLE event (
    event_id               INT AUTO_INCREMENT PRIMARY KEY,
    event_name             VARCHAR(100) NOT NULL,
    category_id            INT NOT NULL,
    description            TEXT,
    rules                  TEXT,
    prizes                 VARCHAR(255),
    venue_id               INT NULL,
    event_date             DATE NOT NULL,
    start_time             TIME NOT NULL,
    end_time               TIME NOT NULL,
    registration_fee       DECIMAL(8,2) NOT NULL DEFAULT 0,
    early_bird_fee         DECIMAL(8,2) NULL,
    early_bird_until       DATETIME NULL,
    registration_deadline  DATETIME NULL,
    max_participants       INT NOT NULL,
    team_min               TINYINT NOT NULL DEFAULT 1,
    team_max               TINYINT NOT NULL DEFAULT 1,
    coordinator_name       VARCHAR(100),
    coordinator_phone      VARCHAR(15),
    status                 ENUM('OPEN','CLOSED','COMPLETED','CANCELLED') NOT NULL DEFAULT 'OPEN',
    is_published           BOOLEAN NOT NULL DEFAULT TRUE,
    results_published      BOOLEAN NOT NULL DEFAULT FALSE,
    change_note            VARCHAR(255) NULL,           -- shown as an "Updated" tag
    changed_at             DATETIME NULL,
    is_demo                BOOLEAN NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_event_name   UNIQUE (event_name),
    CONSTRAINT fk_event_cat    FOREIGN KEY (category_id) REFERENCES event_category(category_id) ON DELETE RESTRICT,
    CONSTRAINT fk_event_venue  FOREIGN KEY (venue_id)    REFERENCES venue(venue_id)             ON DELETE SET NULL,
    CONSTRAINT chk_event_fee   CHECK (registration_fee >= 0),
    CONSTRAINT chk_event_early CHECK (early_bird_fee IS NULL OR (early_bird_fee >= 0 AND early_bird_fee <= registration_fee)),
    CONSTRAINT chk_event_max   CHECK (max_participants > 0),
    CONSTRAINT chk_event_time  CHECK (end_time > start_time),
    CONSTRAINT chk_event_team  CHECK (team_min >= 1 AND team_max >= team_min AND team_max <= 10)
);

-- which staff members coordinate / judge which event
CREATE TABLE event_staff (
    event_id  INT NOT NULL,
    user_id   INT NOT NULL,
    PRIMARY KEY (event_id, user_id),
    CONSTRAINT fk_estaff_event FOREIGN KEY (event_id) REFERENCES event(event_id)   ON DELETE CASCADE,
    CONSTRAINT fk_estaff_user  FOREIGN KEY (user_id)  REFERENCES app_user(user_id) ON DELETE CASCADE
);

CREATE TABLE coupon (
    coupon_id      INT AUTO_INCREMENT PRIMARY KEY,
    code           VARCHAR(30) NOT NULL,
    discount_type  ENUM('PERCENT','FLAT') NOT NULL,
    discount_value DECIMAL(8,2) NOT NULL,
    event_id       INT NULL,                    -- NULL = valid for every event
    max_uses       INT NULL,                    -- NULL = unlimited
    used_count     INT NOT NULL DEFAULT 0,
    valid_until    DATETIME NULL,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_coupon_code UNIQUE (code),
    CONSTRAINT fk_coupon_event FOREIGN KEY (event_id) REFERENCES event(event_id) ON DELETE CASCADE,
    CONSTRAINT chk_coupon_value CHECK (discount_value > 0 AND (discount_type = 'FLAT' OR discount_value <= 100)),
    CONSTRAINT chk_coupon_uses CHECK (max_uses IS NULL OR used_count <= max_uses)
);

-- ---------------------------------------------------------------------
-- 4. REGISTRATIONS, TEAMS, PAYMENTS
-- ---------------------------------------------------------------------
CREATE TABLE registration (
    reg_id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NOT NULL,
    event_id         INT NOT NULL,
    team_name        VARCHAR(60),
    status           ENUM('PENDING','CONFIRMED','WAITLISTED','CANCELLED') NOT NULL DEFAULT 'PENDING',
    fee_amount       DECIMAL(8,2) NOT NULL DEFAULT 0,   -- price after early bird / coupon, fixed at booking
    coupon_id        INT NULL,
    ticket_code      CHAR(12) NOT NULL,                  -- encoded in the QR ticket
    hold_expires_at  DATETIME NULL,                      -- unpaid seat is released after this time
    attended         BOOLEAN NOT NULL DEFAULT FALSE,
    checked_in_at    DATETIME NULL,
    checked_in_by    INT NULL,
    registered_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source           ENUM('ONLINE','DESK') NOT NULL DEFAULT 'ONLINE',
    CONSTRAINT uq_reg_user_event UNIQUE (user_id, event_id),
    CONSTRAINT uq_reg_ticket     UNIQUE (ticket_code),
    CONSTRAINT fk_reg_user    FOREIGN KEY (user_id)       REFERENCES app_user(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_reg_event   FOREIGN KEY (event_id)      REFERENCES event(event_id)   ON DELETE CASCADE,
    CONSTRAINT fk_reg_coupon  FOREIGN KEY (coupon_id)     REFERENCES coupon(coupon_id) ON DELETE SET NULL,
    CONSTRAINT fk_reg_checkin FOREIGN KEY (checked_in_by) REFERENCES app_user(user_id) ON DELETE SET NULL,
    CONSTRAINT chk_reg_fee    CHECK (fee_amount >= 0)
);

-- additional team members (the registering participant is the team leader)
CREATE TABLE team_member (
    member_id    INT AUTO_INCREMENT PRIMARY KEY,
    reg_id       INT NOT NULL,
    member_name  VARCHAR(100) NOT NULL,
    member_email VARCHAR(120),
    member_phone VARCHAR(15),
    CONSTRAINT fk_member_reg FOREIGN KEY (reg_id) REFERENCES registration(reg_id) ON DELETE CASCADE,
    CONSTRAINT chk_member_phone CHECK (member_phone IS NULL OR member_phone REGEXP '^[0-9]{10}$')
);

CREATE TABLE payment (
    payment_id           INT AUTO_INCREMENT PRIMARY KEY,
    reg_id               INT NOT NULL,
    amount               DECIMAL(8,2) NOT NULL,
    method               ENUM('UPI_QR','GATEWAY','CASH','FREE') NOT NULL,
    status               ENUM('PENDING','SUBMITTED','SUCCESS','FAILED','REFUNDED') NOT NULL DEFAULT 'PENDING',
    utr                  VARCHAR(22) NULL,              -- UPI reference number typed by the payer
    gateway_order_id     VARCHAR(40) NULL,
    gateway_payment_id   VARCHAR(40) NULL,
    collected_by         INT NULL,                      -- cashier who took cash / verified
    note                 VARCHAR(255),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at              DATETIME NULL,
    CONSTRAINT uq_payment_utr   UNIQUE (utr),
    CONSTRAINT uq_payment_order UNIQUE (gateway_order_id),
    CONSTRAINT uq_payment_gwpay UNIQUE (gateway_payment_id),
    CONSTRAINT fk_payment_reg   FOREIGN KEY (reg_id)       REFERENCES registration(reg_id) ON DELETE CASCADE,
    CONSTRAINT fk_payment_staff FOREIGN KEY (collected_by) REFERENCES app_user(user_id)    ON DELETE SET NULL,
    CONSTRAINT chk_payment_amount CHECK (amount >= 0),
    CONSTRAINT chk_payment_utr CHECK (utr IS NULL OR utr REGEXP '^[A-Za-z0-9]{8,22}$')
);

-- lines imported from the college bank statement (for UPI reconciliation)
CREATE TABLE bank_txn (
    txn_id              INT AUTO_INCREMENT PRIMARY KEY,
    utr                 VARCHAR(22) NOT NULL,
    amount              DECIMAL(10,2) NOT NULL,
    txn_date            DATE NULL,
    narration           VARCHAR(255),
    matched_payment_id  INT NULL,
    imported_by         INT NULL,
    imported_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_bank_payment FOREIGN KEY (matched_payment_id) REFERENCES payment(payment_id) ON DELETE SET NULL,
    CONSTRAINT fk_bank_user FOREIGN KEY (imported_by) REFERENCES app_user(user_id) ON DELETE SET NULL,
    CONSTRAINT uq_bank_txn_utr UNIQUE (utr)
);

-- ---------------------------------------------------------------------
-- 5. RESULTS, SCORING, FEEDBACK
-- ---------------------------------------------------------------------
CREATE TABLE judge_score (
    reg_id     INT NOT NULL,
    judge_id   INT NOT NULL,
    score      DECIMAL(5,2) NOT NULL,
    remarks    VARCHAR(255),
    scored_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (reg_id, judge_id),
    CONSTRAINT fk_score_reg   FOREIGN KEY (reg_id)   REFERENCES registration(reg_id) ON DELETE CASCADE,
    CONSTRAINT fk_score_judge FOREIGN KEY (judge_id) REFERENCES app_user(user_id)    ON DELETE CASCADE,
    CONSTRAINT chk_score CHECK (score BETWEEN 0 AND 100)
);

CREATE TABLE event_result (
    event_id  INT NOT NULL,
    position  TINYINT NOT NULL,
    reg_id    INT NOT NULL,
    PRIMARY KEY (event_id, position),
    CONSTRAINT uq_result_reg   UNIQUE (reg_id),
    CONSTRAINT fk_result_event FOREIGN KEY (event_id) REFERENCES event(event_id)      ON DELETE CASCADE,
    CONSTRAINT fk_result_reg   FOREIGN KEY (reg_id)   REFERENCES registration(reg_id) ON DELETE CASCADE,
    CONSTRAINT chk_result_pos  CHECK (position BETWEEN 1 AND 3)
);

CREATE TABLE feedback (
    reg_id      INT PRIMARY KEY,
    rating      TINYINT NOT NULL,
    comments    VARCHAR(500),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_feedback_reg FOREIGN KEY (reg_id) REFERENCES registration(reg_id) ON DELETE CASCADE,
    CONSTRAINT chk_feedback_rating CHECK (rating BETWEEN 1 AND 5)
);

-- ---------------------------------------------------------------------
-- 6. COMMUNICATION & AUDIT
-- ---------------------------------------------------------------------
CREATE TABLE news_item (
    news_id     INT AUTO_INCREMENT PRIMARY KEY,
    message     VARCHAR(300) NOT NULL,
    link_url    VARCHAR(255),
    priority    ENUM('INFO','IMPORTANT','URGENT') NOT NULL DEFAULT 'INFO',
    starts_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ends_at     DATETIME NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    is_demo     BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  INT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_news_user FOREIGN KEY (created_by) REFERENCES app_user(user_id) ON DELETE SET NULL,
    CONSTRAINT chk_news_dates CHECK (ends_at IS NULL OR ends_at > starts_at)
);

CREATE TABLE email_outbox (
    mail_id     INT AUTO_INCREMENT PRIMARY KEY,
    to_email    VARCHAR(120) NOT NULL,
    subject     VARCHAR(200) NOT NULL,
    body_text   TEXT NOT NULL,
    body_html   MEDIUMTEXT,
    status      ENUM('QUEUED','SENT','FAILED','DEMO') NOT NULL DEFAULT 'QUEUED',
    attempts    TINYINT NOT NULL DEFAULT 0,
    last_error  VARCHAR(255),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at     DATETIME NULL
);

CREATE TABLE audit_log (
    log_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NULL,
    action      VARCHAR(50) NOT NULL,
    details     VARCHAR(255),
    ip_address  VARCHAR(45),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- 7. INDEXES
-- ---------------------------------------------------------------------
CREATE INDEX idx_event_date         ON event(event_date, start_time);
CREATE INDEX idx_event_status       ON event(status, is_published);
CREATE INDEX idx_reg_event_status   ON registration(event_id, status);
CREATE INDEX idx_reg_hold           ON registration(status, hold_expires_at);
CREATE INDEX idx_payment_status     ON payment(status, method);
CREATE INDEX idx_outbox_status      ON email_outbox(status);
CREATE INDEX idx_news_active        ON news_item(is_active, starts_at);
CREATE INDEX idx_audit_created      ON audit_log(created_at);
CREATE INDEX idx_user_role          ON app_user(role);

-- ---------------------------------------------------------------------
-- 8. FUNCTIONS
-- ---------------------------------------------------------------------
DELIMITER $$

-- seats still available (pending + confirmed hold a seat; waitlisted do not)
CREATE FUNCTION fn_seats_left(p_event_id INT) RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_capacity INT DEFAULT 0;
    DECLARE v_taken    INT DEFAULT 0;
    SELECT max_participants INTO v_capacity FROM event WHERE event_id = p_event_id;
    SELECT COUNT(*) INTO v_taken FROM registration
     WHERE event_id = p_event_id AND status IN ('PENDING','CONFIRMED');
    RETURN v_capacity - v_taken;
END$$

-- current price of an event (early-bird price while the offer is running)
CREATE FUNCTION fn_event_price(p_event_id INT) RETURNS DECIMAL(8,2)
READS SQL DATA
BEGIN
    DECLARE v_fee DECIMAL(8,2);
    DECLARE v_early DECIMAL(8,2);
    DECLARE v_until DATETIME;
    SELECT registration_fee, early_bird_fee, early_bird_until INTO v_fee, v_early, v_until
      FROM event WHERE event_id = p_event_id;
    IF v_early IS NOT NULL AND v_until IS NOT NULL AND NOW() <= v_until THEN
        RETURN v_early;
    END IF;
    RETURN v_fee;
END$$

-- ---------------------------------------------------------------------
-- 9. TRIGGERS   (@restoring = 1 during backup restore skips side effects)
-- ---------------------------------------------------------------------
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

-- capacity guard: a seat-holding registration cannot exceed the event capacity
CREATE TRIGGER trg_registration_before_insert
BEFORE INSERT ON registration
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);
    IF @restoring IS NULL AND NEW.status IN ('PENDING','CONFIRMED') THEN
        SELECT status INTO v_status FROM event WHERE event_id = NEW.event_id;
        IF v_status IS NOT NULL THEN
            IF v_status <> 'OPEN' THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registrations are closed for this event.';
            END IF;
            IF fn_seats_left(NEW.event_id) <= 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Sorry, this event is already full.';
            END IF;
        END IF;
    END IF;
END$$

-- a successful payment confirms the registration
CREATE TRIGGER trg_payment_after_insert
AFTER INSERT ON payment
FOR EACH ROW
BEGIN
    IF @restoring IS NULL AND NEW.status = 'SUCCESS' THEN
        UPDATE registration SET status = 'CONFIRMED', hold_expires_at = NULL
         WHERE reg_id = NEW.reg_id AND status = 'PENDING';
    END IF;
END$$

-- payment verified later (UPI / cash) confirms; refund cancels
CREATE TRIGGER trg_payment_after_update
AFTER UPDATE ON payment
FOR EACH ROW
BEGIN
    IF @restoring IS NULL THEN
        IF NEW.status = 'SUCCESS' AND OLD.status <> 'SUCCESS' THEN
            UPDATE registration SET status = 'CONFIRMED', hold_expires_at = NULL
             WHERE reg_id = NEW.reg_id AND status = 'PENDING';
        ELSEIF NEW.status = 'REFUNDED' AND OLD.status <> 'REFUNDED' THEN
            UPDATE registration SET status = 'CANCELLED' WHERE reg_id = NEW.reg_id;
        END IF;
    END IF;
END$$

-- audit trail of registration status / attendance changes
CREATE TRIGGER trg_registration_after_update
AFTER UPDATE ON registration
FOR EACH ROW
BEGIN
    IF @restoring IS NULL THEN
        IF NEW.status <> OLD.status THEN
            INSERT INTO audit_log (user_id, action, details)
            VALUES (NEW.user_id, 'REG_STATUS',
                    CONCAT('Reg #', NEW.reg_id, ' : ', OLD.status, ' -> ', NEW.status));
        END IF;
        IF NEW.attended <> OLD.attended THEN
            INSERT INTO audit_log (user_id, action, details)
            VALUES (NEW.checked_in_by, 'ATTENDANCE',
                    CONCAT('Reg #', NEW.reg_id, ' marked ', IF(NEW.attended, 'PRESENT', 'ABSENT')));
        END IF;
    END IF;
END$$

-- keeps coupon usage counts correct
CREATE TRIGGER trg_registration_after_insert
AFTER INSERT ON registration
FOR EACH ROW
BEGIN
    IF @restoring IS NULL AND NEW.coupon_id IS NOT NULL THEN
        UPDATE coupon SET used_count = used_count + 1 WHERE coupon_id = NEW.coupon_id;
    END IF;
END$$

CREATE TRIGGER trg_event_after_delete
AFTER DELETE ON event
FOR EACH ROW
BEGIN
    IF @restoring IS NULL THEN
        INSERT INTO audit_log (user_id, action, details)
        VALUES (NULL, 'EVENT_DELETED', CONCAT('Event #', OLD.event_id, ' "', OLD.event_name, '" deleted'));
    END IF;
END$$

-- ---------------------------------------------------------------------
-- 10. STORED PROCEDURES
-- ---------------------------------------------------------------------

-- promotes the oldest waitlisted registration of an event if a seat is free
CREATE PROCEDURE sp_promote_waitlist(IN p_event_id INT, IN p_hold_minutes INT, OUT p_promoted_reg INT)
BEGIN
    DECLARE v_reg INT DEFAULT NULL;
    SET p_promoted_reg = NULL;
    IF fn_seats_left(p_event_id) > 0 THEN
        SELECT reg_id INTO v_reg FROM registration
         WHERE event_id = p_event_id AND status = 'WAITLISTED'
         ORDER BY registered_at, reg_id LIMIT 1 FOR UPDATE;
        IF v_reg IS NOT NULL THEN
            UPDATE registration
               SET status = IF(fee_amount = 0, 'CONFIRMED', 'PENDING'),
                   hold_expires_at = IF(fee_amount = 0, NULL, NOW() + INTERVAL p_hold_minutes MINUTE)
             WHERE reg_id = v_reg;
            UPDATE payment SET status = 'SUCCESS', paid_at = NOW()
             WHERE reg_id = v_reg AND method = 'FREE' AND status = 'PENDING';
            SET p_promoted_reg = v_reg;
        END IF;
    END IF;
END$$

-- admin-only cancellation: refund successful payments, fail pending ones, free the seat
CREATE PROCEDURE sp_cancel_registration(IN p_reg_id INT, IN p_actor_id INT, IN p_reason VARCHAR(200))
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
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot cancel - the participant has already checked in.';
    END IF;

    UPDATE payment SET status = 'REFUNDED' WHERE reg_id = p_reg_id AND status = 'SUCCESS' AND amount > 0;
    UPDATE payment SET status = 'FAILED', note = 'Cancelled by admin'
     WHERE reg_id = p_reg_id AND status IN ('PENDING','SUBMITTED');
    UPDATE registration SET status = 'CANCELLED', hold_expires_at = NULL WHERE reg_id = p_reg_id;
    DELETE FROM event_result WHERE reg_id = p_reg_id;

    INSERT INTO audit_log (user_id, action, details)
    VALUES (p_actor_id, 'CANCEL', CONCAT('Cancelled reg #', p_reg_id, ': ', IFNULL(p_reason, '')));
    COMMIT;
END$$

-- releases seats whose payment was never started / submitted in time
CREATE PROCEDURE sp_expire_holds(OUT p_expired INT)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    START TRANSACTION;
    UPDATE payment p JOIN registration r ON r.reg_id = p.reg_id
       SET p.status = 'FAILED', p.note = 'Payment time expired'
     WHERE r.status = 'PENDING' AND r.hold_expires_at IS NOT NULL AND r.hold_expires_at < NOW()
       AND p.status = 'PENDING';
    UPDATE registration r
       SET r.status = 'CANCELLED', r.hold_expires_at = NULL
     WHERE r.status = 'PENDING' AND r.hold_expires_at IS NOT NULL AND r.hold_expires_at < NOW()
       AND NOT EXISTS (SELECT 1 FROM payment p WHERE p.reg_id = r.reg_id AND p.status IN ('SUBMITTED','SUCCESS'));
    SET p_expired = ROW_COUNT();
    COMMIT;
END$$

DELIMITER ;

-- ---------------------------------------------------------------------
-- 11. VIEWS
-- ---------------------------------------------------------------------
CREATE VIEW v_latest_payment AS
SELECT p.*
  FROM payment p
 WHERE p.payment_id = (SELECT MAX(p2.payment_id) FROM payment p2 WHERE p2.reg_id = p.reg_id);

CREATE VIEW v_event_summary AS
SELECT e.event_id, e.event_name, c.category_name, e.category_id, v.venue_name, e.venue_id,
       e.event_date, e.start_time, e.end_time, e.registration_fee, e.early_bird_fee,
       e.early_bird_until, e.registration_deadline, e.max_participants, e.team_min, e.team_max,
       e.status, e.is_published, e.results_published, e.description, e.rules, e.prizes,
       e.coordinator_name, e.coordinator_phone, e.change_note, e.changed_at, e.is_demo,
       fn_event_price(e.event_id) AS current_price,
       COUNT(CASE WHEN r.status IN ('PENDING','CONFIRMED') THEN 1 END)    AS registered,
       COUNT(CASE WHEN r.status = 'CONFIRMED' THEN 1 END)                  AS confirmed,
       COUNT(CASE WHEN r.status = 'WAITLISTED' THEN 1 END)                 AS waitlisted,
       COUNT(CASE WHEN r.attended AND r.status = 'CONFIRMED' THEN 1 END)   AS attended,
       e.max_participants - COUNT(CASE WHEN r.status IN ('PENDING','CONFIRMED') THEN 1 END) AS seats_left,
       COALESCE(SUM(CASE WHEN lp.status = 'SUCCESS' THEN lp.amount END), 0) AS revenue
  FROM event e
  JOIN event_category c    ON c.category_id = e.category_id
  LEFT JOIN venue v        ON v.venue_id = e.venue_id
  LEFT JOIN registration r ON r.event_id = e.event_id
  LEFT JOIN v_latest_payment lp ON lp.reg_id = r.reg_id
 GROUP BY e.event_id;

CREATE VIEW v_registration_details AS
SELECT r.reg_id, r.user_id, r.event_id, r.team_name, r.status, r.attended, r.checked_in_at,
       r.registered_at, r.ticket_code, r.fee_amount, r.hold_expires_at, r.source,
       u.full_name, u.email, u.phone,
       c.college_name, d.dept_name, pp.year_of_study,
       e.event_name, e.event_date, e.start_time, e.end_time, e.results_published,
       cat.category_name, v.venue_name,
       lp.payment_id, lp.method AS payment_method, lp.amount, lp.status AS payment_status,
       lp.utr, lp.gateway_payment_id, lp.paid_at,
       er.position AS result_position,
       (SELECT COUNT(*) FROM team_member tm WHERE tm.reg_id = r.reg_id) + 1 AS team_size
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

CREATE VIEW v_participant_details AS
SELECT u.user_id, u.full_name, u.email, u.phone, u.is_active, u.email_verified, u.created_at,
       u.last_login, u.is_demo, c.college_name, d.dept_name, pp.year_of_study, pp.gender,
       pp.college_id, pp.dept_id,
       (SELECT COUNT(*) FROM registration r
         WHERE r.user_id = u.user_id AND r.status IN ('PENDING','CONFIRMED')) AS active_registrations
  FROM app_user u
  JOIN participant_profile pp ON pp.user_id = u.user_id
  JOIN college c    ON c.college_id = pp.college_id
  JOIN department d ON d.dept_id = pp.dept_id
 WHERE u.role = 'PARTICIPANT';

CREATE VIEW v_college_leaderboard AS
SELECT c.college_id, c.college_name,
       COUNT(DISTINCT pp.user_id) AS participants,
       COUNT(DISTINCT CASE WHEN r.status = 'CONFIRMED' THEN r.reg_id END) AS registrations,
       COUNT(DISTINCT CASE WHEN er.position = 1 AND e.results_published THEN er.reg_id END) AS gold,
       COUNT(DISTINCT CASE WHEN er.position = 2 AND e.results_published THEN er.reg_id END) AS silver,
       COUNT(DISTINCT CASE WHEN er.position = 3 AND e.results_published THEN er.reg_id END) AS bronze,
       COUNT(DISTINCT CASE WHEN er.position = 1 AND e.results_published THEN er.reg_id END) * 5
     + COUNT(DISTINCT CASE WHEN er.position = 2 AND e.results_published THEN er.reg_id END) * 3
     + COUNT(DISTINCT CASE WHEN er.position = 3 AND e.results_published THEN er.reg_id END) * 1 AS points
  FROM college c
  LEFT JOIN participant_profile pp ON pp.college_id = c.college_id
  LEFT JOIN registration r         ON r.user_id = pp.user_id
  LEFT JOIN event_result er        ON er.reg_id = r.reg_id
  LEFT JOIN event e                ON e.event_id = er.event_id
 GROUP BY c.college_id, c.college_name;

CREATE VIEW v_score_board AS
SELECT r.event_id, r.reg_id, u.full_name, r.team_name, c.college_name,
       COUNT(js.judge_id) AS judges, ROUND(AVG(js.score), 2) AS avg_score
  FROM registration r
  JOIN app_user u ON u.user_id = r.user_id
  LEFT JOIN participant_profile pp ON pp.user_id = u.user_id
  LEFT JOIN college c ON c.college_id = pp.college_id
  LEFT JOIN judge_score js ON js.reg_id = r.reg_id
 WHERE r.status = 'CONFIRMED' AND r.attended
 GROUP BY r.event_id, r.reg_id, u.full_name, r.team_name, c.college_name;
