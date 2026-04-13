import streamlit as st
import pandas as pd
import database as db
from scheduler import generate_schedule
from exporter import generate_excel_bytes

st.set_page_config(page_title="Medical Resident Scheduler", layout="wide", page_icon="🏥")
MONTH_NAMES = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]

# --- Initial Mock Data Hydration ---
if not db.fetch_all("Residents"):
    db.add_resident('Alice', 1); db.add_resident('Bob', 1); db.add_resident('Charlie', 2)
    db.add_resident('David', 5); db.add_resident('Eve', 5)
    db.add_rotation('General Wards', 1, 4, 1, 2, 0, 2)
    db.add_rotation('ICU', 1, 2, 0, 1, 1, 2)
    db.add_rotation('Nights', 1, 2, 0, 1, 0, 1)
    db.add_rotation('Elective', 0, 5, 0, 99, 0, 99)
    db.add_elective('Cardiology')
    db.add_pgy_requirement(1, 'Elective', 3, 3)
    db.add_pgy_requirement(2, 'Elective', 4, 4)
    db.add_pgy_requirement(5, 'Elective', 4, 5)
    db.add_forbidden_adjacency('ICU', 'Nights')
    # Pre-populate Self-Adjacencies to prevent back-to-back blocks
    db.add_forbidden_adjacency('ICU', 'ICU')
    db.add_forbidden_adjacency('Nights', 'Nights')

st.title("🏥 Medical Resident Scheduler")

# Track globally if any grid holds un-saved states.
def check_unsaved():
    keys_map = {
        'res_del': 'Residents', 
        'rot_edit': 'Rotations', 
        'el_del': 'Electives', 
        'req_del': 'Soft Requests', 
        'hb_del': 'Hard Mappings'
    }
    has_unsaved = []
    for key, name in keys_map.items():
        state = st.session_state.get(key, {})
        if state.get('edited_rows') or state.get('added_rows') or state.get('deleted_rows'):
            has_unsaved.append(name)
    if has_unsaved:
        st.warning(f"⚠️ **Warning**: You have un-synced deletions or edits waiting inside: `{', '.join(has_unsaved)}`. Please remember to click their 'Save/Sync' buttons before switching tabs or calculating a schedule!")

check_unsaved()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🗓️ Generator", "👥 Residents", "🔄 Rotations", "🩺 Electives", 
    "🎓 PGY Rules", "⛔ Adjacencies", "💡 Requests & Blocks"
])

def render_table(table_name):
    """Helper to fetch and clean dataframe by dropping internal SQLite ID"""
    data = db.fetch_all(table_name)
    if data:
        df = pd.DataFrame(data)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No records found.")

def highlight_hard_blocks(row, hb_list):
    """Pandas styler: Highlights cell red if it matches a hard block assignment"""
    styles = [''] * len(row)
    res_name = row.get('Resident')
    if not res_name: return styles
    
    for idx, col in enumerate(row.index):
        if col in MONTH_NAMES:
            m_idx = MONTH_NAMES.index(col)
            val = row[col]
            for hb in hb_list:
                if hb['resident_name'] == res_name and hb['rotation_name'] == val and hb['month'] == m_idx:
                    styles[idx] = 'background-color: rgba(255, 100, 100, 0.6); color: white;'
    return styles

# --- 1: GENERATE ---
with tab1:
    res = db.fetch_all("Residents")
    rots = db.fetch_all("Rotations")
    elecs = db.fetch_all("Electives")
    pgy = db.fetch_all("Pgy_Requirements")
    reqs = db.fetch_all("Requests")
    hb = db.fetch_all("Hard_Blocks")
    adj = db.fetch_all("Forbidden_Adjacencies")

    # Backup & Restore DB
    bc1, bc2 = st.columns(2)
    with bc1:
        try:
            with open(db.DB_PATH, "rb") as f:
                st.download_button("💾 Backup Full System Config (.db)", data=f, file_name="scheduler_backup.db", mime="application/x-sqlite3")
        except FileNotFoundError:
            pass
    with bc2:
        uploaded_db = st.file_uploader("📥 Import Database Backup", type=["db"])
        if uploaded_db is not None:
            if st.button("🚨 Overwrite System", type="primary"):
                with open(db.DB_PATH, "wb") as f:
                    f.write(uploaded_db.getbuffer())
                st.success("System Restored! Rebooting..."); st.rerun()
    st.markdown("---")

    # Load previously generated grid if it survived reboot
    hist_df = db.load_schedule()
    if not hist_df.empty:
        st.subheader("💾 Last Saved Schedule")
        
        # Apply styler
        styled_hist = hist_df.style.apply(highlight_hard_blocks, axis=1, hb_list=hb)
        st.dataframe(styled_hist, use_container_width=True, hide_index=True)
        
        st.download_button(
            label="📥 Download Saved Schedule Excel",
            data=generate_excel_bytes(hist_df),
            file_name="Master_Schedule.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary"
        )
        st.markdown("---")

    if st.button("🚀 Generate New Optimized Schedule", type="primary"):
        with st.spinner("Crunching OR-Tools Constraints (Stand by... solver is looking for the optimal permutation)..."):
            success, df, status = generate_schedule(res, rots, elecs, pgy, reqs, hb, adj)
            
            if success:
                db.save_schedule(df)
                st.success(f"Optimal Schedule Built! (Status: {status})")
                st.rerun()
            else:
                st.error(f"Infeasible! Constraints collide. (Status: {status})")

# --- 2: RESIDENTS ---
with tab2:
    with st.form("f_res"):
        c1, c2 = st.columns(2)
        n = c1.text_input("Name")
        y = c2.number_input("PGY Year", 1, 7, 1)
        if st.form_submit_button("Add Resident") and n:
            db.add_resident(n, y); st.rerun()
    
    res_data = db.fetch_all("Residents")
    if res_data:
        df_res = pd.DataFrame(res_data)
        ed_res = st.data_editor(df_res, use_container_width=True, hide_index=True, column_config={"id": None}, num_rows="dynamic", key="res_del")
        if st.button("💾 Sync Resident Edits", key="s_res"):
            db.clear_all("Residents")
            for _, row in ed_res.iterrows():
                db.add_resident(row['name'], row['year_pgy'])
            if 'res_del' in st.session_state: del st.session_state['res_del']
            st.rerun()

# --- 3: ROTATIONS ---
with tab3:
    st.info("💡 You can interact directly with the spreadsheet below to change limits! Just hit Save when you're done.")
    with st.expander("➕ Add New Rotation"):
        with st.form("f_rot"):
            n = st.text_input("Rotation Name", help="E.g. Wards, ICU")
            c1,c2,c3,c4 = st.columns(4)
            mn_t = c1.number_input("Min Total",0,99,0); mx_t = c1.number_input("Max Total",0,99,99)
            mn_i = c2.number_input("Min Interns",0,99,0); mx_i = c2.number_input("Max Interns",0,99,99)
            mn_s = c3.number_input("Min Seniors",0,99,0); mx_s = c3.number_input("Max Seniors",0,99,99)
            if st.form_submit_button("Add Rotation") and n:
                db.add_rotation(n, mn_t, mx_t, mn_i, mx_i, mn_s, mx_s); st.rerun()
    
    # Interactive Data Editor
    rot_data = db.fetch_all("Rotations")
    if rot_data:
        rot_df = pd.DataFrame(rot_data)
        # Use column_config to hide ID but keep it accessible programmatically
        edited_df = st.data_editor(rot_df, use_container_width=True, hide_index=True, column_config={"id": None}, num_rows="dynamic", key="rot_edit")
        if st.button("💾 Save Table Edits", type="primary"):
            db.clear_all("Rotations")
            for _, row in edited_df.iterrows():
                db.add_rotation(row['name'], row['min_total'], row['max_total'], row['min_interns'], row['max_interns'], row['min_seniors'], row['max_seniors'])
            if 'rot_edit' in st.session_state: del st.session_state['rot_edit']
            st.success("Saved successfully!")
            st.rerun()
    else:
        st.info("No rotations found.")

# --- 4: ELECTIVES ---
with tab4:
    with st.form("f_elec"):
        n = st.text_input("Elective Name", help="Will auto-prefix with elective-")
        if st.form_submit_button("Add") and n:
            db.add_elective(n); st.rerun()
            
    elec_data = db.fetch_all("Electives")
    if elec_data:
        df_e = pd.DataFrame(elec_data)
        ed_elec = st.data_editor(df_e, use_container_width=True, hide_index=True, column_config={"id": None}, num_rows="dynamic", key="el_del")
        if st.button("💾 Sync Elective Edits", key="s_el"):
            db.clear_all("Electives")
            for _, row in ed_elec.iterrows():
                db.add_elective(row['name'])
            if 'el_del' in st.session_state: del st.session_state['el_del']
            st.rerun()

# --- 5: PGY RULES ---
with tab5:
    with st.form("f_pgy"):
        c1, c2, c3, c4 = st.columns(4)
        y = c1.number_input("PGY Level", 1, 7)
        r = c2.selectbox("Rotation", [x['name'] for x in db.fetch_all("Rotations")])
        mn = c3.number_input("Min Months", 0, 12, 1)
        mx = c4.number_input("Max Months", 0, 12, 1)
        if st.form_submit_button("Add PGY Rule"):
            db.add_pgy_requirement(y, r, mn, mx); st.rerun()
    render_table("Pgy_Requirements")

# --- 6: ADJACENCIES ---
with tab6:
    st.markdown("Prevent two rotations from ever touching.")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("f_adj"):
            r1 = st.selectbox("Rotation A", [x['name'] for x in db.fetch_all("Rotations")])
            r2 = st.selectbox("Rotation B", [x['name'] for x in db.fetch_all("Rotations")])
            if st.form_submit_button("Add Blocked Sequence") and r1 and r2:
                db.add_forbidden_adjacency(r1, r2); st.rerun()
    with c2:
        with st.form("d_adj"):
            adj_data = db.fetch_all("Forbidden_Adjacencies")
            adj_str_map = {f"{a['rotation_1']} -> {a['rotation_2']}": a['id'] for a in adj_data}
            d_sel = st.selectbox("Rule to Remove", list(adj_str_map.keys()) if adj_str_map else [""])
            if st.form_submit_button("Delete Sequence") and d_sel:
                db.delete_row("Forbidden_Adjacencies", adj_str_map[d_sel])
                st.rerun()
    render_table("Forbidden_Adjacencies")

# --- 7: REQUESTS & HARD BLOCKS ---
with tab7:
    def display_mapping_warnings():
        reqs = db.fetch_all("Requests")
        hbs = db.fetch_all("Hard_Blocks")
        from collections import defaultdict
        
        hb_trk = defaultdict(list)
        req_trk = defaultdict(list)
        for h in hbs: hb_trk[(h['resident_name'], h['month'])].append(h['rotation_name'])
        for r in reqs: req_trk[(r['resident_name'], r['month'])].append(r['rotation_name'])
            
        for (res, m), rots in hb_trk.items():
            m_name = MONTH_NAMES[m]
            if len(rots) > 1:
                st.error(f"🚨 **Critical Hard Block Collision**: {res} is locked to multiple rotations ({', '.join(rots)}) in {m_name}! The schedule will fail to generate.")
            if (res, m) in req_trk:
                req_rots = req_trk[(res, m)]
                st.warning(f"⚠️ **Inefficient Mapping**: {res} has a Hard Block (`{rots[0]}`) AND a Soft Request (`{', '.join(req_rots)}`) assigned for {m_name}. The Hard Block will overpower the request, making it useless.")

    display_mapping_warnings()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Soft Requests")
        with st.form("f_req"):
            res_list = [x['name'] for x in db.fetch_all("Residents")]
            rot_list = [x['name'] for x in db.fetch_all("Rotations")] + [f"elective-{x['name']}" for x in db.fetch_all("Electives")]
            r = st.selectbox("Resident", res_list if res_list else [""])
            rot = st.selectbox("Requested Block", rot_list if rot_list else [""])
            m = st.selectbox("Month", range(12), format_func=lambda x: MONTH_NAMES[x] if x < 12 else "")
            w = st.selectbox("Choice", [1,2,3], format_func=lambda x:f"{x} Choice")
            if st.form_submit_button("Save Request") and r and rot:
                db.add_request(r, rot, m, {1:10, 2:5, 3:2}[w]); st.rerun()
        
        req_data = db.fetch_all("Requests")
        if req_data:
            df_r = pd.DataFrame(req_data)
            ed_req = st.data_editor(df_r, use_container_width=True, hide_index=True, column_config={"id": None}, num_rows="dynamic", key="req_del")
            if st.button("💾 Sync Request Deletions", key="s_req"):
                db.clear_all("Requests")
                for _, row in ed_req.iterrows():
                    db.add_request(row['resident_name'], row['rotation_name'], row['month'], row['weight'])
                if 'req_del' in st.session_state: del st.session_state['req_del']
                st.rerun()
        
    with c2:
        st.subheader("Hard Mappings")
        with st.form("f_hb"):
            r_h = st.selectbox("Resident", res_list if res_list else [""], key="hb_r")
            rot_h = st.selectbox("Rotation", rot_list if rot_list else [""], key="hb_rot")
            m_h = st.selectbox("Month", range(12), format_func=lambda x: MONTH_NAMES[x] if x < 12 else "", key="hb_m")
            if st.form_submit_button("Lock Mapping") and r_h and rot_h:
                db.add_hard_block(r_h, rot_h, m_h); st.rerun()
        
        hb_data = db.fetch_all("Hard_Blocks")
        if hb_data:
            df_h = pd.DataFrame(hb_data)
            ed_hb = st.data_editor(df_h, use_container_width=True, hide_index=True, column_config={"id": None}, num_rows="dynamic", key="hb_del")
            if st.button("💾 Sync Mapping Deletions", key="s_hb"):
                db.clear_all("Hard_Blocks")
                for _, row in ed_hb.iterrows():
                    db.add_hard_block(row['resident_name'], row['rotation_name'], row['month'])
                if 'hb_del' in st.session_state: del st.session_state['hb_del']
                st.rerun()
