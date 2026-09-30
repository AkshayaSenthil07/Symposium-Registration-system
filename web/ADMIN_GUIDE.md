# Admin guide - running the symposium

Everything below is done from the website. No code changes are needed.

## Before registrations open
1. **Settings:** set the symposium name, dates, address and contact details, logo, UPI ID, payment methods and policy texts.
2. **Venues & lists:** add your halls with their capacities; check the categories and departments.
3. **Events:** add each event.
   - **Team size:** 1–1 means an individual event, 2–4 means a team of 2 to 4.
   - **Fee and early bird:** the fee is per team for team events. The early-bird price needs an end date.
   - **Capacity and deadline:** a maximum number of seats (or teams), and an online registration deadline.
   - **Visibility:** untick "Show on the public website" to prepare an event privately.
4. **Staff accounts:** create cashier and coordinator accounts. Each gets a temporary password to share privately and must change it at first sign-in.
5. **Coordinators:** in each event's edit page, tick the coordinators and judges for that event.
6. **Coupons (optional):** percent or flat discounts, limited to an event or a number of uses.
7. **Flash news:** post "Registrations are open!".

## While registrations are open
- **UPI QR payments:** students pay the college UPI ID and type the UPI reference.
  - Staff > **Payments** lists the references waiting for verification.
  - Download the account statement as **CSV** from net banking and upload it. Matching references are confirmed and e-mailed automatically; re-uploading is safe.
  - Or verify a reference by hand, but only after you have seen the money in the account.
- **Unpaid seats:** they are released automatically after the hold time in Settings. Waitlisted students then get the seat and an e-mail.
- **Changing an event's date, time or venue:** keep "announce" ticked. The change appears in the flash news and every registrant gets an e-mail. The event shows an "Updated" tag for a week.
- **Cancelling an event:** set its status to CANCELLED. Registrants are e-mailed. Refund paid registrations from Registrations > open > Cancel & refund.

## On the event day
- **Registration desk (cashier):**
  1. Search the student, or create a new account (they get an e-mail to set a password).
  2. Tick the events and collect cash or UPI.
  3. Print or show the receipt with its QR ticket.
- **Check-in (anyone on staff):**
  - Open **QR check-in** on a phone (Chrome on Android) and scan tickets with the camera.
  - A USB scanner works on a laptop, or type the 12-character code.
  - Unpaid and already-used tickets are rejected.
  - Scanning a ticket with the phone's normal camera app also opens the check-in page.
- **Attendance sheet:** Staff > Registrations > pick the event > Attendance sheet (PDF), with a signature column.
- **Cash report:** Staff > Cash report shows what each cashier collected today. Use it to hand over cash.

## After each event
1. **Scoring:** judges open Scoring & results and enter scores from 0 to 100 for attendees.
2. **Winners:** choose them, or click "Use top 3 by score", then **Publish results**.
3. **What publishing does:**
   - The winners appear on the public Results page.
   - College points are added to the championship.
   - Every attendee is e-mailed that their certificate is ready.
4. **Certificates:** they carry a QR and ID that anyone can verify at `/verify/<id>`.

## Safety
- **Automatic backups:** every 30 minutes. Admin > **Backups** > Download one to a pen drive before the event day.
- **Restoring:** it replaces all data. A safety backup of the current data is taken first.
- **Audit log:** shows every sign-in, payment, check-in and change.

## Demo vs live
- **Admin > Demo / go live > Load demo data:** adds sample events, people and payments for presentations. Everything it adds is flagged as demo.
- **Go live:**
  - It deletes every participant, registration, payment and e-mail, plus the demo events, news, coupons and staff.
  - It keeps venues, lists, settings, real events and real staff, and takes a backup first.
  - You need a real admin account before you can go live.
- **The demo gateway never works in live mode:** "Pay online" appears only after real Razorpay keys are entered.

## Where things are stored
- **Settings, events and all data:** in the MySQL database.
- **Secrets** (database passwords, Razorpay keys, SMTP password): in `web/instance/config.ini` on the server only.
