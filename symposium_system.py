import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector

# --- DATABASE CONNECTION ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",       # Change to your MySQL username
            password="password", # Change to your MySQL password
            database="SymposiumDB"
        )
        return conn
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"Error connecting to database: {err}")
        return None

# --- MAIN LOGIN WINDOW ---
class LoginApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Symposium Registration System - Login")
        self.root.geometry("350x200")
        
        tk.Label(root, text="Symposium Login", font=("Arial", 16, "bold")).pack(pady=10)
        
        tk.Button(root, text="Admin Login", width=20, command=self.open_admin).pack(pady=5)
        tk.Button(root, text="Participant Portal", width=20, command=self.open_participant).pack(pady=5)

    def open_admin(self):
        self.root.destroy()
        admin_root = tk.Tk()
        AdminDashboard(admin_root)

    def open_participant(self):
        self.root.destroy()
        part_root = tk.Tk()
        ParticipantDashboard(part_root)

# --- ADMIN DASHBOARD ---
class AdminDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Admin Dashboard")
        self.root.geometry("900x600")
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()

        # Notebook for Tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        self.setup_events_tab()
        self.setup_reports_tab()

    def setup_events_tab(self):
        """Tab for CRUD operations on Events"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Manage Events")

        # Input Fields
        fields_frame = ttk.LabelFrame(tab, text="Event Details")
        fields_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(fields_frame, text="Event Name:").grid(row=0, column=0, padx=5, pady=5)
        self.ent_event_name = ttk.Entry(fields_frame)
        self.ent_event_name.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(fields_frame, text="Date (YYYY-MM-DD):").grid(row=0, column=2, padx=5, pady=5)
        self.ent_event_date = ttk.Entry(fields_frame)
        self.ent_event_date.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(fields_frame, text="Fee:").grid(row=1, column=0, padx=5, pady=5)
        self.ent_event_fee = ttk.Entry(fields_frame)
        self.ent_event_fee.grid(row=1, column=1, padx=5, pady=5)

        # Buttons (CRUD)
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10)
        ttk.Button(btn_frame, text="Add Event", command=self.add_event).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Update Event", command=self.update_event).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Delete Event", command=self.delete_event).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Refresh List", command=self.load_events).pack(side='left', padx=5)

        # Treeview (Table display)
        self.tree_events = ttk.Treeview(tab, columns=("ID", "Name", "Date", "Fee"), show="headings")
        self.tree_events.heading("ID", text="Event ID")
        self.tree_events.heading("Name", text="Event Name")
        self.tree_events.heading("Date", text="Date")
        self.tree_events.heading("Fee", text="Fee")
        self.tree_events.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.tree_events.bind("<<TreeviewSelect>>", self.on_event_select)
        self.load_events()

    def load_events(self):
        for row in self.tree_events.get_children():
            self.tree_events.delete(row)
        self.cursor.execute("SELECT event_id, event_name, event_date, registration_fee FROM Event")
        for r in self.cursor.fetchall():
            self.tree_events.insert("", 'end', values=r)

    def on_event_select(self, event):
        selected = self.tree_events.selection()[0]
        values = self.tree_events.item(selected, 'values')
        self.ent_event_name.delete(0, tk.END)
        self.ent_event_name.insert(0, values[1])
        self.ent_event_date.delete(0, tk.END)
        self.ent_event_date.insert(0, values[2])
        self.ent_event_fee.delete(0, tk.END)
        self.ent_event_fee.insert(0, values[3])
        self.selected_event_id = values[0]

    def add_event(self):
        name, date, fee = self.ent_event_name.get(), self.ent_event_date.get(), self.ent_event_fee.get()
        if not (name and date and fee):
            messagebox.showwarning("Input Error", "All fields are required!")
            return
        # SQL Operation 1: INSERT
        self.cursor.execute("INSERT INTO Event (event_name, event_date, registration_fee) VALUES (%s, %s, %s)", (name, date, fee))
        self.conn.commit()
        messagebox.showinfo("Success", "Event Added!")
        self.load_events()

    def update_event(self):
        if not hasattr(self, 'selected_event_id'):
            messagebox.showwarning("Error", "Select an event to update!")
            return
        name, date, fee = self.ent_event_name.get(), self.ent_event_date.get(), self.ent_event_fee.get()
        # SQL Operation 2: UPDATE
        self.cursor.execute("UPDATE Event SET event_name=%s, event_date=%s, registration_fee=%s WHERE event_id=%s", 
                            (name, date, fee, self.selected_event_id))
        self.conn.commit()
        messagebox.showinfo("Success", "Event Updated!")
        self.load_events()

    def delete_event(self):
        if not hasattr(self, 'selected_event_id'):
            messagebox.showwarning("Error", "Select an event to delete!")
            return
        # SQL Operation 3: DELETE
        self.cursor.execute("DELETE FROM Event WHERE event_id=%s", (self.selected_event_id,))
        self.conn.commit()
        messagebox.showinfo("Success", "Event Deleted!")
        self.load_events()

    def setup_reports_tab(self):
        """Tab for Aggregate Queries and Reports"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Reports & Analytics")

        ttk.Label(tab, text="Event-wise Participation & Revenue Report", font=("Arial", 12, "bold")).pack(pady=10)
        ttk.Button(tab, text="Generate Report", command=self.generate_report).pack(pady=5)

        self.tree_report = ttk.Treeview(tab, columns=("Event", "Total_Reg", "Total_Revenue", "Status"), show="headings")
        self.tree_report.heading("Event", text="Event Name")
        self.tree_report.heading("Total_Reg", text="Total Registrations")
        self.tree_report.heading("Total_Revenue", text="Total Revenue")
        self.tree_report.heading("Status", text="Avg Status")
        self.tree_report.pack(fill='both', expand=True, padx=10, pady=10)

    def generate_report(self):
        for row in self.tree_report.get_children():
            self.tree_report.delete(row)
        
        # SQL Operation 4: JOIN, AGGREGATE (COUNT, SUM), and GROUP BY
        query = """
            SELECT 
                e.event_name, 
                COUNT(r.reg_id) as total_regs, 
                COALESCE(SUM(p.amount), 0) as total_revenue,
                AVG(CASE WHEN r.status = 'Confirmed' THEN 1 ELSE 0 END) as confirmation_rate
            FROM Event e
            LEFT JOIN Registration r ON e.event_id = r.event_id
            LEFT JOIN Payment p ON r.reg_id = p.reg_id
            GROUP BY e.event_id, e.event_name
        """
        self.cursor.execute(query)
        for r in self.cursor.fetchall():
            rate = "High" if r[3] and r[3] > 0.5 else "Low" if r[3] else "N/A"
            self.tree_report.insert("", 'end', values=(r[0], r[1], f"₹{r[2]:.2f}", rate))

# --- PARTICIPANT DASHBOARD ---
class ParticipantDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Participant Portal")
        self.root.geometry("800x500")
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()
        self.participant_id = None

        self.setup_registration_ui()
        self.setup_my_registrations_ui()

    def setup_registration_ui(self):
        frame = ttk.LabelFrame(self.root, text="New Registration")
        frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(frame, text="First Name:").grid(row=0, column=0, padx=5, pady=5)
        self.ent_fname = ttk.Entry(frame)
        self.ent_fname.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Email:").grid(row=0, column=2, padx=5, pady=5)
        self.ent_email = ttk.Entry(frame)
        self.ent_email.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame, text="Select Event:").grid(row=1, column=0, padx=5, pady=5)
        self.cmb_events = ttk.Combobox(frame, state="readonly")
        self.cmb_events.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky='ew')
        self.load_events_dropdown()

        ttk.Button(frame, text="Register & Pay", command=self.register_and_pay).grid(row=2, column=0, columnspan=4, pady=10)

    def load_events_dropdown(self):
        self.cursor.execute("SELECT event_id, event_name, registration_fee FROM Event")
        self.events_data = self.cursor.fetchall()
        self.cmb_events['values'] = [f"{e[1]} (₹{e[2]})" for e in self.events_data]

    def register_and_pay(self):
        fname, email = self.ent_fname.get(), self.ent_email.get()
        event_idx = self.cmb_events.current()
        
        if not (fname and email and event_idx != -1):
            messagebox.showwarning("Error", "Please fill all details and select an event!")
            return

        event_id, event_name, fee = self.events_data[event_idx]

        try:
            # FIX: Disable autocommit to safely handle transactions without getting stuck
            self.conn.autocommit = False

            # Check if participant exists, else insert
            self.cursor.execute("SELECT part_id FROM Participant WHERE email = %s", (email,))
            result = self.cursor.fetchone()
            
            if result:
                self.participant_id = result[0]
            else:
                # Insert Participant
                self.cursor.execute("INSERT INTO Participant (first_name, last_name, email) VALUES (%s, 'User', %s)", (fname, email))
                self.participant_id = self.cursor.lastrowid

            # Insert Registration
            self.cursor.execute("INSERT INTO Registration (part_id, event_id, status) VALUES (%s, %s, 'Pending')", 
                                (self.participant_id, event_id))
            reg_id = self.cursor.lastrowid

            # Insert Payment
            self.cursor.execute("INSERT INTO Payment (reg_id, amount, payment_status) VALUES (%s, %s, 'Success')", 
                                (reg_id, fee))
            
            # Commit Transaction
            self.conn.commit()
            messagebox.showinfo("Success", f"Registration Successful!\nReg ID: {reg_id}\nPayment of ₹{fee} processed.")
            self.load_my_registrations()
            
        except mysql.connector.Error as err:
            # Rollback on failure
            self.conn.rollback()
            messagebox.showerror("Transaction Failed", f"Error: {err}")
        finally:
            # Restore autocommit to True so other operations work normally
            self.conn.autocommit = True

    def setup_my_registrations_ui(self):
        frame = ttk.LabelFrame(self.root, text="My Registrations & Payment Status")
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        ttk.Button(frame, text="Refresh My Details", command=self.load_my_registrations).pack(pady=5)

        self.tree_my_regs = ttk.Treeview(frame, columns=("RegID", "Event", "Date", "Status", "Payment"), show="headings")
        self.tree_my_regs.heading("RegID", text="Reg ID")
        self.tree_my_regs.heading("Event", text="Event Name")
        self.tree_my_regs.heading("Date", text="Reg Date")
        self.tree_my_regs.heading("Status", text="Reg Status")
        self.tree_my_regs.heading("Payment", text="Payment Status")
        self.tree_my_regs.pack(fill='both', expand=True, padx=10, pady=10)

    def load_my_registrations(self):
        if not self.participant_id:
            return
        
        for row in self.tree_my_regs.get_children():
            self.tree_my_regs.delete(row)

        # SQL Operation 5: SUBQUERY / JOIN to fetch specific participant details
        query = """
            SELECT r.reg_id, e.event_name, r.reg_date, r.status, p.payment_status
            FROM Registration r
            JOIN Event e ON r.event_id = e.event_id
            LEFT JOIN Payment p ON r.reg_id = p.reg_id
            WHERE r.part_id = %s
        """
        self.cursor.execute(query, (self.participant_id,))
        for r in self.cursor.fetchall():
            self.tree_my_regs.insert("", 'end', values=r)

if __name__ == "__main__":
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()