-- Create Database
CREATE DATABASE IF NOT EXISTS SymposiumDB;
USE SymposiumDB;

-- 1. College Table
CREATE TABLE College (
    college_id INT AUTO_INCREMENT PRIMARY KEY,
    college_name VARCHAR(100) NOT NULL UNIQUE
);

-- 2. Department Table
CREATE TABLE Department (
    dept_id INT AUTO_INCREMENT PRIMARY KEY,
    dept_name VARCHAR(100) NOT NULL,
    college_id INT,
    FOREIGN KEY (college_id) REFERENCES College(college_id) ON DELETE CASCADE
);

-- 3. Venue Table (Capacity and Location)
CREATE TABLE Venue (
    venue_id INT AUTO_INCREMENT PRIMARY KEY,
    venue_name VARCHAR(100) NOT NULL,
    location VARCHAR(100),
    capacity INT CHECK (capacity > 0)
);

-- 4. Event Table
CREATE TABLE Event (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    description TEXT,
    venue_id INT,
    event_date DATE NOT NULL,
    registration_fee DECIMAL(10,2) CHECK (registration_fee >= 0),
    FOREIGN KEY (venue_id) REFERENCES Venue(venue_id) ON DELETE SET NULL
);

-- 5. Participant Table
CREATE TABLE Participant (
    part_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone VARCHAR(15),
    dept_id INT,
    FOREIGN KEY (dept_id) REFERENCES Department(dept_id) ON DELETE SET NULL
);

-- 6. Registration Table (Central Table)
CREATE TABLE Registration (
    reg_id INT AUTO_INCREMENT PRIMARY KEY,
    part_id INT,
    event_id INT,
    reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('Pending', 'Confirmed', 'Cancelled') DEFAULT 'Pending',
    FOREIGN KEY (part_id) REFERENCES Participant(part_id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES Event(event_id) ON DELETE CASCADE,
    UNIQUE KEY unique_reg (part_id, event_id) -- Prevents duplicate registrations
);

-- 7. Payment Table
CREATE TABLE Payment (
    pay_id INT AUTO_INCREMENT PRIMARY KEY,
    reg_id INT,
    amount DECIMAL(10,2) NOT NULL,
    payment_status ENUM('Success', 'Failed', 'Refunded') DEFAULT 'Success',
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reg_id) REFERENCES Registration(reg_id) ON DELETE CASCADE
);

-- 8. Admin Table
CREATE TABLE Admin (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);

-- DBMS Concepts: INDEXES
CREATE INDEX idx_event_date ON Event(event_date);
CREATE INDEX idx_participant_email ON Participant(email);

-- DBMS Concepts: VIEW (Joins Participant, Department, and College)
CREATE VIEW Participant_Details_View AS
SELECT 
    p.part_id, p.first_name, p.last_name, p.email, 
    d.dept_name, c.college_name
FROM Participant p
LEFT JOIN Department d ON p.dept_id = d.dept_id
LEFT JOIN College c ON d.college_id = c.college_id;

-- DBMS Concepts: TRIGGER (Auto-confirm registration when payment is successful)
DELIMITER //
CREATE TRIGGER trg_after_payment_insert
AFTER INSERT ON Payment
FOR EACH ROW
BEGIN
    IF NEW.payment_status = 'Success' THEN
        UPDATE Registration SET status = 'Confirmed' WHERE reg_id = NEW.reg_id;
    END IF;
END;
//
DELIMITER ;

-- Insert Dummy Data for Testing
INSERT INTO College (college_name) VALUES ('Engineering College'), ('Arts & Science College');
INSERT INTO Department (dept_name, college_id) VALUES ('Computer Science', 1), ('Mechanical', 1), ('Physics', 2);
INSERT INTO Venue (venue_name, location, capacity) VALUES ('Main Auditorium', 'Block A', 500), ('Seminar Hall 1', 'Block B', 100);
INSERT INTO Event (event_name, description, venue_id, event_date, registration_fee) VALUES 
('Paper Presentation', 'Present your research', 1, '2026-10-15', 200.00),
('Coding Hackathon', '24hr coding event', 2, '2026-10-16', 300.00);
INSERT INTO Admin (username, password_hash) VALUES ('admin', 'admin123');