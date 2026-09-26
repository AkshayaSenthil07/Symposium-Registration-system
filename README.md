# Symposium Registration System

A complete desktop-based Symposium Management System built with Python (Tkinter) and MySQL. It allows participants to register for events, make payments, and view their dashboard, while providing admins with tools to manage events, view analytics, and generate reports.

## Features
- **Participant Portal:** Register for events, process mock payments, and view registration/payment status.
- **Admin Dashboard:** CRUD operations for Events, and Analytics/Reports (Event-wise participation and revenue).
- **Database Concepts:** Implements Normalization, Foreign Keys, Constraints, Indexes, Views, Triggers, and Transactions.

## Tech Stack
- **Frontend:** Python (Tkinter GUI)
- **Backend/Database:** MySQL
- **Connector:** `mysql-connector-python`

## Setup Instructions

### 1. Database Setup
1. Open MySQL Workbench or your preferred MySQL client.
2. Run the SQL script located in `database_schema.sql` to create the database, tables, views, and triggers.
3. Update the database credentials in `symposium_system.py` (lines 12-15) if your username/password differ from `root`/`password`.

### 2. Python Setup
1. Ensure you have Python 3.x installed.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt