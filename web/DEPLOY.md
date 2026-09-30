# Putting the website on the internet

This guide assumes a small Linux server (VPS) or a college server with a public IP. Any host that
runs Python 3.10+ and MySQL 8 works. Budget: the smallest VPS is enough for a college symposium.

## 1. Before you start
- **Domain:** a domain or sub-domain, e.g. `symposium.yourcollege.edu`, pointing (DNS "A record") to the server's IP.
- **MySQL 8.0:** installed on the server, bound to localhost only (the default).
- **Python and git:** Python 3.10+ and `git`.

## 2. Install
```bash
git clone <your repo> symposium && cd symposium/web
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py init-db            # MySQL root password (not stored) + your admin e-mail and password
```
`init-db` creates:
- the database;
- a limited MySQL user for the site;
- a read-only user for the SQL console;
- `instance/config.ini`, which holds all the secrets.

**Back up `instance/config.ini` safely and never commit it.**

Edit `instance/config.ini`:
```ini
[server]
base_url = https://symposium.yourcollege.edu
https = true
behind_proxy = true
```

## 3. Run the app as a service
`/etc/systemd/system/symposium.service`:
```ini
[Unit]
Description=Symposium website
After=network.target mysql.service

[Service]
WorkingDirectory=/home/ubuntu/symposium/web
ExecStart=/home/ubuntu/symposium/web/.venv/bin/python manage.py run --host 127.0.0.1 --port 8000
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now symposium
```

## 4. HTTPS in front (Caddy - gets free certificates automatically)
```bash
sudo apt install caddy
```
`/etc/caddy/Caddyfile`:
```
symposium.yourcollege.edu {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 6MB
    }
}
```
```bash
sudo systemctl reload caddy
```
HTTPS is required for secure cookies, for the camera QR scanner on phones and for Razorpay.

## 5. Firewall
Allow only SSH, HTTP and HTTPS:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```
MySQL (3306) must **not** be open to the internet.

## 6. Payments
**UPI QR (free):**
1. In Admin > Settings > Payments, enter the college's UPI ID (e.g. `cseassoc@okaxis`) and the payee name.
2. Test by paying ₹1 to yourself through a registration, then submitting the reference.

**Razorpay (optional, instant confirmation):**
1. Complete KYC in the Razorpay dashboard for the college or association account.
2. In the dashboard, enable only **UPI** and **Netbanking**.
3. Create API keys and, in Admin > Settings, choose **LIVE**, then paste the Key ID and Key secret.
4. In the dashboard > Webhooks, add `https://symposium.yourcollege.edu/pay/razorpay/webhook` for the event `payment.captured`, and put the same secret in Admin > Settings.
5. Make one real ₹1 payment and refund it from the Razorpay dashboard.

## 7. E-mail
In Admin > Settings > E-mail, choose SMTP.
- **Gmail:** host `smtp.gmail.com`, port 587. Use an *App password* (Google account > Security > 2-step verification > App passwords).
- Click **Save & test connection**. Until then, e-mails wait in Admin > E-mail outbox.

## 8. Backups
- **Automatic:** backups run every 30 minutes into `web/instance/backups/`; the last 48 are kept.
- **Off the server:** copy them off the server daily, e.g. with a cron `rsync`, or download from Admin > Backups.
- **Full database dump (optional):** `mysqldump --single-transaction --routines --triggers symposium_live > dump.sql` (run as root).

## 9. Going live checklist
1. Create your real admin account, sign in with it, and change the demo settings.
2. Enter the events, venues, fees, dates and deadlines.
3. Set the UPI ID, gateway keys and SMTP, and check the policy texts.
4. Go to Admin > Demo / go live and click **Go live**. This removes all demo data and takes a backup first.
5. Register once yourself with a real ₹1 test event, check in with the QR, then delete the test event.
6. Download a backup to a pen drive.

## Updating the site later
```bash
git pull
pip install -r requirements.txt
sudo systemctl restart symposium
```
