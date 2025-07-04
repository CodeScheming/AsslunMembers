import streamlit as st
import pandas as pd
import qrcode
from PIL import Image
import io
import uuid
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import database as db
import cv2  # OpenCV for drawing on the video feed
import numpy as np
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
import threading
import time

# --- App Configuration ---
st.set_page_config(page_title="Member Management System", layout="wide")

# --- Thread-Safe Container for Scanner Result ---
# This is necessary because the webrtc component runs in a separate thread.
result_lock = threading.Lock()
scanned_member_id_container = {"id": None}

# --- RTC Configuration for Deployment ---
# This helps the video stream work better on deployed servers (like Streamlit Cloud)
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# --- Helper Functions ---
def calculate_age(born):
    """Calculates age from a date object."""
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def generate_qr_code(data):
    """Generates a QR code image from data and returns it as bytes."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    byte_im = buf.getvalue()
    return byte_im

# --- Super Admin Authentication ---
def login():
    """A simple login form for the super admin."""
    st.title("Member Management System")
    st.subheader("Super Admin Login")
    with st.form("login_form"):
        username = st.text_input("Username").lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        # In a real app, use st.secrets for secure credential management
        if submitted:
            if username == "asslun10" and password == "Asslun@123":
                st.session_state["logged_in"] = True
                st.rerun() 
            else:
                st.error("Incorrect username or password")

# --- QR Code Scanner Video Callback (OpenCV Version) ---
def video_frame_callback(frame):
    """
    Decodes QR codes using OpenCV's built-in detector.
    This avoids the need for the external ZBar library.
    """
    img = frame.to_ndarray(format="bgr24")
    
    # Initialize the QRCodeDetector
    qr_decoder = cv2.QRCodeDetector()
    
    # Detect and decode the QR code
    data, bbox, _ = qr_decoder.detectAndDecode(img)
    
    if bbox is not None and data:
        # `bbox` is a numpy array of float points
        points = bbox[0]
        # Convert points to integer for drawing
        pts = np.array([points], np.int32).reshape((-1, 1, 2))
        
        # Check if it's a valid Member ID format
        if data.startswith("MEM-"):
            with result_lock:
                scanned_member_id_container["id"] = data
            
            # Draw a green box and text for a successful scan
            cv2.polylines(img, [pts], True, (0, 255, 0), 3)
            cv2.putText(img, "Member Found!", (int(points[0][0]), int(points[0][1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        else:
            # Draw a red box for an invalid QR code
            cv2.polylines(img, [pts], True, (0, 0, 255), 3)
            cv2.putText(img, "Invalid QR Code", (int(points[0][0]), int(points[0][1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
    return frame.from_ndarray(img, format="bgr24")
# --- Main Application UI ---
def main_app():
    st.sidebar.title(f"Welcome, Admin!")
    st.sidebar.markdown("---")
    
    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "View/Manage Members", "Add New Member", "Manage Departments"]
    )
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        # Clear all session state on logout
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    if page == "Dashboard":
        display_dashboard()
    elif page == "View/Manage Members":
        display_manage_members()
    elif page == "Add New Member":
        display_add_member()
    elif page == "Manage Departments":
        display_manage_departments()

def display_dashboard():
    st.title("📊 Dashboard")
    st.markdown("---")
    
    all_members = db.get_all_members()
    total_members = len(all_members)
    
    renewals_due_next_30_days = 0
    expired_members = 0  # New variable for expired members
    if all_members:
        today = date.today()
        for member in all_members:
            renewal_date = datetime.strptime(member['next_renewal_date'], "%Y-%m-%d").date()
            if 0 <= (renewal_date - today).days <= 30:
                renewals_due_next_30_days += 1
            if renewal_date < today:
                expired_members += 1  # Count expired members
            
    col1, col2, col3 = st.columns(3)  # Add a third column for expired members
    col1.metric("Total Members", f"{total_members} 👥")
    col2.metric("Renewals Due (Next 30 Days)", f"{renewals_due_next_30_days} 🗓️")
    col3.metric("Expired Members", f"{expired_members} ❌")  # Display expired members

    st.subheader("Recent Members")
    if all_members:
        # Convert list of sqlite3.Row objects to list of dicts for Pandas
        members_list_of_dicts = [dict(row) for row in all_members]
        df = pd.DataFrame(members_list_of_dicts)
        st.dataframe(df[['member_id', 'name', 'department', 'member_since', 'next_renewal_date']].tail(), use_container_width=True)
    else:
        st.info("No members found.")

def display_add_member():
    st.title("➕ Add New Member")
    st.markdown("---")
    
    departments = db.get_all_departments()
    if not departments:
        st.warning("No departments found. Please add a department in 'Manage Departments' first.")
        return

    with st.form("add_member_form", clear_on_submit=True):
        st.subheader("Personal Details")
        name = st.text_input("Full Name *", placeholder="John Doe")
        dob = st.date_input("Date of Birth *", min_value=date(1940, 1, 1), max_value=date.today() - relativedelta(years=18))
        profile_pic_file = st.file_uploader("Upload Profile Picture", type=['png', 'jpg', 'jpeg'])

        st.subheader("Contact Details")
        email = st.text_input("Email Address", placeholder="john.doe@example.com")
        phone = st.text_input("Phone Number", placeholder="+1234567890")
        address = st.text_area("Address")
        
        st.subheader("Membership Details")
        department = st.selectbox("Department *", options=departments)
        member_since = st.date_input("Member Since", value=date.today())
        
        submitted = st.form_submit_button("Add Member")

        if submitted:
            if not name or not dob or not department:
                st.error("Please fill in all required fields (*).")
            else:
                member_id = f"MEM-{uuid.uuid4().hex[:8].upper()}"
                profile_pic_bytes = profile_pic_file.read() if profile_pic_file else None
                next_renewal_date = member_since + relativedelta(years=1)
                
                member_data = {
                    "member_id": member_id, "name": name, "dob": dob.strftime("%Y-%m-%d"),
                    "email": email, "phone": phone, "address": address, "department": department,
                    "member_since": member_since.strftime("%Y-%m-%d"),
                    "next_renewal_date": next_renewal_date.strftime("%Y-%m-%d"),
                    "profile_pic": profile_pic_bytes
                }
                
                db.add_member(member_data)
                st.success(f"Successfully added member: {name} (ID: {member_id})")
                st.balloons()

def display_manage_members():
    st.title("🔍 View / Manage Members")

    # Initialize session state for this page
    if "show_scanner" not in st.session_state: st.session_state.show_scanner = False
    if "selected_member_id" not in st.session_state: st.session_state.selected_member_id = None

    members = db.get_all_members()
    if not members:
        st.warning("No members found. Please add a new member.")
        return

    member_dict = {f"{m['name']} ({m['member_id']})": m['member_id'] for m in members}
    member_id_to_display = {v: k for k, v in member_dict.items()}

    # --- SEARCH AND SCANNER UI ---
    search_col, scan_col = st.columns([3, 1])
    with search_col:
        search_query = st.text_input("Search by Name or ID", key="search_text")
    with scan_col:
        st.write("")
        st.write("")
        if st.button("📷 Scan QR to Search", use_container_width=True):
            # Toggle scanner and reset any previous result
            st.session_state.show_scanner = not st.session_state.show_scanner
            with result_lock:
                scanned_member_id_container["id"] = None
            st.rerun()

    # --- DISPLAY QR SCANNER AND POLLING LOGIC ---
    if st.session_state.show_scanner:
        st.subheader("QR Code Scanner")
        webrtc_ctx = webrtc_streamer(key="qr-scanner", mode=WebRtcMode.SENDRECV,
                                     rtc_configuration=RTC_CONFIGURATION,
                                     video_frame_callback=video_frame_callback,
                                     media_stream_constraints={"video": True, "audio": False},
                                     async_processing=True)
        
        status_indicator = st.empty()

        # This block is the core of the solution. It actively polls for a result.
        if webrtc_ctx.state.playing:
            status_indicator.info("Camera is active. Looking for a QR code...")
            
            # Loop to check for the scanned ID from the callback
            while True:
                with result_lock:
                    scanned_id = scanned_member_id_container["id"]
                
                if scanned_id:
                    member = db.get_member_by_id(scanned_id)
                    if member:
                        # --- SUCCESS: ID FOUND AND VALID ---
                        status_indicator.success(f"Member Found: {member['name']}. Loading...")
                        st.session_state.selected_member_id = scanned_id
                        st.session_state.show_scanner = False
                        
                        # Clean up the container for the next scan
                        with result_lock:
                            scanned_member_id_container["id"] = None
                        
                        # Give user a moment to see the success message before rerun
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        # --- ERROR: ID SCANNED BUT NOT IN DATABASE ---
                        status_indicator.error(f"Error: Member ID '{scanned_id}' not found. Please scan another code.")
                        with result_lock:
                            scanned_member_id_container["id"] = None # Reset for re-scan
                        time.sleep(3) # Wait for user to read the message
                        status_indicator.info("Camera is active. Looking for a QR code...") # Reset message
                
                # Check if the component has been stopped manually by the user
                if not webrtc_ctx.state.playing:
                    st.session_state.show_scanner = False
                    st.rerun()
                    
                time.sleep(0.2)  # Poll every 200ms to be responsive without high CPU usage
        else:
            status_indicator.warning("Camera is not active. Please grant permissions and start.")

    # --- MEMBER SELECTION AND DISPLAY LOGIC (This part is now driven by the scanner) ---
    filtered_members = {k: v for k, v in member_dict.items() if search_query.lower() in k.lower()} if search_query else member_dict
    
    selected_index = 0
    if st.session_state.selected_member_id and st.session_state.selected_member_id in member_id_to_display:
        display_name = member_id_to_display[st.session_state.selected_member_id]
        if display_name in filtered_members:
            selected_index = list(filtered_members.keys()).index(display_name)
    
    if not filtered_members:
        st.warning("No members match your search criteria.")
        return
        
    selected_display = st.selectbox("Select a Member", options=list(filtered_members.keys()), index=selected_index, key="member_selector")
    if selected_display:
        st.session_state.selected_member_id = filtered_members[selected_display]

    # --- DISPLAY MEMBER DETAILS AND ACTIONS ---
    if st.session_state.selected_member_id:
        member = db.get_member_by_id(st.session_state.selected_member_id)
        if not member:
            st.error("Selected member not found. They may have been deleted.")
            st.session_state.selected_member_id = None
            return

        st.markdown("---")
        info_col, qr_col = st.columns([2, 1])
        with info_col:
            st.subheader(f"**{member['name']}**")
            dob = datetime.strptime(member['dob'], "%Y-%m-%d").date()
            st.markdown(f"**Member ID:** `{member['member_id']}`\n\n"
                        f"**Age:** {calculate_age(dob)}\n\n"
                        f"**Department:** {member['department']}\n\n"
                        f"**Email:** {member['email'] or 'N/A'}\n\n"
                        f"**Phone:** {member['phone'] or 'N/A'}\n\n"
                        f"**Address:** {member['address'] or 'N/A'}\n\n"
                        f"**Member Since:** {datetime.strptime(member['member_since'], '%Y-%m-%d').strftime('%B %d, %Y')}")
            
            renewal_date = datetime.strptime(member['next_renewal_date'], '%Y-%m-%d').date()
            if renewal_date < date.today():
                st.error(f"**Next Renewal Date:** {renewal_date.strftime('%B %d, %Y')} (EXPIRED)")
            else:
                st.success(f"**Next Renewal Date:** {renewal_date.strftime('%B %d, %Y')}")
        with qr_col:
            if member['profile_pic']:
                st.image(member['profile_pic'], caption="Profile Picture", width=200)
            
            qr_bytes = generate_qr_code(member['member_id'])
            st.image(qr_bytes, caption="Member ID QR Code", width=200)
            st.download_button(label="Download QR Code", data=qr_bytes, file_name=f"{member['member_id']}_qr.png", mime="image/png")

        # --- TABS FOR ACTIONS ---
        tab1, tab2, tab3, tab4 = st.tabs(["🔄 Renewal System", "✏️ Edit Profile", "📜 Renewal History", "❌ Delete Member"])
        with tab1:
            if st.button("Renew Membership for 1 Year"):
                current_renewal = datetime.strptime(member['next_renewal_date'], "%Y-%m-%d").date()
                new_renewal = current_renewal + relativedelta(years=1)
                db.update_renewal_date(member['member_id'], new_renewal.strftime("%Y-%m-%d"))
                db.add_renewal_record(member['member_id'], new_renewal.strftime("%Y-%m-%d"), current_renewal.strftime("%Y-%m-%d"))
                st.success(f"Membership renewed! New expiry: {new_renewal.strftime('%B %d, %Y')}")
                st.rerun()

        with tab2:
            with st.form(f"edit_{member['member_id']}"):
                departments = db.get_all_departments()
                new_name = st.text_input("Name", value=member['name'])
                new_dob = st.date_input("Date of Birth", value=dob)
                new_email = st.text_input("Email", value=member['email'])
                new_phone = st.text_input("Phone", value=member['phone'])
                new_address = st.text_area("Address", value=member['address'])
                new_dept = st.selectbox("Department", options=departments, index=departments.index(member['department']) if member['department'] in departments else 0)
                new_pic = st.file_uploader("Update Profile Picture", type=['png', 'jpg', 'jpeg'])
                if st.form_submit_button("Save Changes"):
                    updated_data = {"name": new_name, "dob": new_dob.strftime("%Y-%m-%d"), "email": new_email, "phone": new_phone,
                                    "address": new_address, "department": new_dept, "profile_pic": new_pic.read() if new_pic else member['profile_pic']}
                    db.update_member(member['member_id'], updated_data)
                    st.success("Member details updated successfully!")
                    st.rerun()

        with tab3:
            history = db.get_renewal_history(member['member_id'])
            if not history:
                st.info("No renewal history found for this member.")
            else:
                for i, record in enumerate(history):
                    renewed_to = datetime.strptime(record['renewal_date'], '%Y-%m-%d').date()
                    renewed_from = datetime.strptime(record['previous_renewal_date'], '%Y-%m-%d').date()
                    st.markdown(f"**Renewed from** `{renewed_from.strftime('%b %d, %Y')}` **to** `{renewed_to.strftime('%b %d, %Y')}`")
                    if i == 0: # Only show revert for the most recent renewal
                        if st.button("↩️ Revert this renewal (Undo)", key=f"revert_{record['id']}", help="Correct a mistaken renewal."):
                            db.revert_last_renewal(record['id'], member['member_id'], record['previous_renewal_date'])
                            st.warning("Renewal has been reverted.")
                            st.rerun()
                    st.markdown("---")

        with tab4:
            st.warning("⚠️ This action is irreversible. All data for this member will be permanently deleted.")
            if st.checkbox(f"I confirm I want to delete {member['name']}", key=f"delete_confirm_{member['member_id']}"):
                if st.button("DELETE PERMANENTLY", type="primary"):
                    db.delete_member(member['member_id'])
                    st.success(f"Member {member['name']} has been deleted.")
                    st.session_state.selected_member_id = None
                    st.rerun()

def display_manage_departments():
    st.title("🏢 Manage Departments")
    st.markdown("---")
    departments = db.get_all_departments()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add New Department")
        with st.form("add_dept_form", clear_on_submit=True):
            new_dept_name = st.text_input("Department Name")
            if st.form_submit_button("Add Department"):
                if new_dept_name and new_dept_name.strip():
                    db.add_department(new_dept_name.strip())
                    st.success(f"Department '{new_dept_name.strip()}' added.")
                    st.rerun()
                else:
                    st.error("Department name cannot be empty.")
    
    with col2:
        st.subheader("Current Departments")
        if not departments:
            st.info("No departments to display.")
        else:
            df = pd.DataFrame(departments, columns=["Department Name"])
            st.dataframe(df, use_container_width=True, hide_index=True)

# --- App Entry Point ---
if __name__ == "__main__":
    db.init_db()  # Ensure database and tables exist on first run
    
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
        
    if st.session_state["logged_in"]:
        main_app()
    else:
        login()