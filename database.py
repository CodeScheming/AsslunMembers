import sqlite3
from datetime import date
import io
import pandas as pd

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect('members.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Members Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            dob TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            department TEXT,
            member_since TEXT NOT NULL,
            next_renewal_date TEXT NOT NULL,
            profile_pic BLOB
        )
    ''')
    
    # Departments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    # Renewal History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS renewal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id TEXT NOT NULL,
            renewal_date TEXT NOT NULL,
            previous_renewal_date TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY (member_id) REFERENCES members (member_id)
        )
    ''')
    
    # Check if default departments exist
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] == 0:
        default_departments = ['Tech', 'Literature', 'HR', 'Finance', 'Admin']
        for dept in default_departments:
            cursor.execute("INSERT OR IGNORE INTO departments (name) VALUES (?)", (dept,))

    conn.commit()
    conn.close()

# --- Member Functions ---
def add_member(member_data):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO members (member_id, name, dob, email, phone, address, department, member_since, next_renewal_date, profile_pic)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        member_data['member_id'], member_data['name'], member_data['dob'], member_data['email'],
        member_data['phone'], member_data['address'], member_data['department'],
        member_data['member_since'], member_data['next_renewal_date'], member_data['profile_pic']
    ))
    conn.commit()
    conn.close()

def get_all_members():
    conn = get_db_connection()
    members = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    conn.close()
    return members

def get_member_by_id(member_id):
    conn = get_db_connection()
    member = conn.execute('SELECT * FROM members WHERE member_id = ?', (member_id,)).fetchone()
    conn.close()
    return member

def update_member(member_id, member_data):
    conn = get_db_connection()
    conn.execute('''
        UPDATE members
        SET name = ?, dob = ?, email = ?, phone = ?, address = ?, department = ?, profile_pic = ?
        WHERE member_id = ?
    ''', (
        member_data['name'], member_data['dob'], member_data['email'],
        member_data['phone'], member_data['address'], member_data['department'],
        member_data['profile_pic'], member_id
    ))
    conn.commit()
    conn.close()

def delete_member(member_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM members WHERE member_id = ?', (member_id,))
    conn.execute('DELETE FROM renewal_history WHERE member_id = ?', (member_id,)) # Also clear history
    conn.commit()
    conn.close()
    
def update_renewal_date(member_id, new_renewal_date):
    conn = get_db_connection()
    conn.execute('UPDATE members SET next_renewal_date = ? WHERE member_id = ?', (new_renewal_date, member_id))
    conn.commit()
    conn.close()

# --- Department Functions ---
def get_all_departments():
    conn = get_db_connection()
    depts = conn.execute('SELECT name FROM departments ORDER BY name').fetchall()
    conn.close()
    return [d['name'] for d in depts]

def add_department(name):
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO departments (name) VALUES (?)', (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        # Department already exists
        pass
    finally:
        conn.close()

def delete_department(name):
    conn = get_db_connection()
    conn.execute('DELETE FROM departments WHERE name = ?', (name,))
    conn.commit()
    conn.close()

# --- Renewal History Functions ---
def add_renewal_record(member_id, renewal_date, previous_renewal_date):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO renewal_history (member_id, renewal_date, previous_renewal_date) 
        VALUES (?, ?, ?)
    ''', (member_id, renewal_date, previous_renewal_date))
    conn.commit()
    conn.close()

def get_renewal_history(member_id):
    conn = get_db_connection()
    history = conn.execute('''
        SELECT id, renewal_date, previous_renewal_date 
        FROM renewal_history WHERE member_id = ? ORDER BY renewal_date DESC
    ''', (member_id,)).fetchall()
    conn.close()
    return history

def revert_last_renewal(history_id, member_id, previous_renewal_date):
    """Reverts the last renewal by deleting the history record and updating the member's renewal date."""
    conn = get_db_connection()
    # Update member's renewal date back to the previous one
    conn.execute('UPDATE members SET next_renewal_date = ? WHERE member_id = ?', (previous_renewal_date, member_id))
    # Delete the mistaken renewal from history
    conn.execute('DELETE FROM renewal_history WHERE id = ?', (history_id,))
    conn.commit()
    conn.close()