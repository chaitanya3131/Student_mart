# StudentMart — Student Marketplace

## How to Run

```bash
pip install flask requests
python app.py
```
Then open: http://127.0.0.1:5000

## Make Yourself Admin
```bash
python -c "import sqlite3; conn = sqlite3.connect('database.db'); conn.execute(\"UPDATE users SET is_admin=1 WHERE email='chaitanyasatpute729@gmail.com'\"); conn.commit(); conn.close(); print('Done!')"
```

## Features
- Buy & Sell student items
- Product status: Available / Reserved / Sold
- SMS notification to seller via Twilio (already configured)
- Admin panel at /admin
- Statistics dashboard at /dashboard
- AI Recommendations at /recommendations

## SMS Setup (Twilio - already configured)
Your Twilio credentials are already filled in app.py.
When a buyer contacts a seller, an SMS is sent to the seller's phone.

NOTE: Twilio free trial only sends SMS to verified numbers.
To send to any number, upgrade your Twilio account.
