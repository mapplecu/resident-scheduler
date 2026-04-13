from ortools.sat.python import cp_model
import pandas as pd

def generate_schedule(residents, rotations, electives, pgy_rules, requests, hard_blocks, adjacencies):
    if not residents or not rotations:
        return False, None, "Must have at least one resident and one rotation."

    num_months = 12
    months = range(num_months)
    month_names = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]

    # --- Build Rotation Indices ---
    all_rotations = []
    # Base rotations
    for rot in rotations:
        r_copy = dict(rot)
        r_copy['_is_elective'] = (r_copy['name'].lower() == 'elective')
        all_rotations.append(r_copy)
        
    # Inject specific electives
    for elec in electives:
        all_rotations.append({
            'name': f"elective-{elec['name']}",
            'min_total': 0, 'max_total': 999,
            'min_interns': 0, 'max_interns': 999,
            'min_seniors': 0, 'max_seniors': 999,
            '_is_elective': True
        })

    rotation_indices = range(len(all_rotations))
    resident_indices = range(len(residents))

    model = cp_model.CpModel()

    # Variables: shifts[(r, m, s)]
    shifts = {}
    for r in resident_indices:
        for m in months:
            for s in rotation_indices:
                shifts[(r, m, s)] = model.NewBoolVar(f'shift_r{r}_m{m}_s{s}')

    # --- Constraints ---

    # 1. One rotation per resident per month
    for r in resident_indices:
        for m in months:
            model.AddExactlyOne(shifts[(r, m, s)] for s in rotation_indices)

    # 2. Coverage Quotas (Min/Max Interns and Seniors)
    generic_elective_caps = next((rot for rot in rotations if rot['name'].lower() == 'elective'), None)

    for m in months:
        # We need to track the master Electives pool if a generic elective exists
        total_electives_in_month = []
        total_elec_interns_in_month = []
        total_elec_seniors_in_month = []

        for s, rot_data in enumerate(all_rotations):
            r_in_rot = []
            int_in_rot = []
            sen_in_rot = []
            
            for r, res_data in enumerate(residents):
                shift_var = shifts[(r, m, s)]
                r_in_rot.append(shift_var)
                
                is_senior = (res_data['year_pgy'] >= 2)
                if is_senior:
                    sen_in_rot.append(shift_var)
                else:
                    int_in_rot.append(shift_var)

            # Record if it's an elective for the master pool, but don't apply bounds to the generic "Elective" single row.
            # We will apply bounds to the merged pool later.
            if rot_data['_is_elective']:
                total_electives_in_month.extend(r_in_rot)
                total_elec_interns_in_month.extend(int_in_rot)
                total_elec_seniors_in_month.extend(sen_in_rot)
            
            # Apply individual rotation constraints (skip generic 'Elective' as it represents the pool limit)
            if rot_data['name'].lower() != 'elective':
                if rot_data.get('min_total', 0) > 0: model.Add(sum(r_in_rot) >= rot_data['min_total'])
                if rot_data.get('max_total', 999) < 999: model.Add(sum(r_in_rot) <= rot_data['max_total'])
                if rot_data.get('min_interns', 0) > 0: model.Add(sum(int_in_rot) >= rot_data['min_interns'])
                if rot_data.get('max_interns', 999) < 999: model.Add(sum(int_in_rot) <= rot_data['max_interns'])
                if rot_data.get('min_seniors', 0) > 0: model.Add(sum(sen_in_rot) >= rot_data['min_seniors'])
                if rot_data.get('max_seniors', 999) < 999: model.Add(sum(sen_in_rot) <= rot_data['max_seniors'])

        # Master Elective Pool Limits
        if generic_elective_caps:
            if generic_elective_caps.get('min_total', 0) > 0: model.Add(sum(total_electives_in_month) >= generic_elective_caps['min_total'])
            if generic_elective_caps.get('max_total', 999) < 999: model.Add(sum(total_electives_in_month) <= generic_elective_caps['max_total'])
            if generic_elective_caps.get('min_interns', 0) > 0: model.Add(sum(total_elec_interns_in_month) >= generic_elective_caps['min_interns'])
            if generic_elective_caps.get('max_interns', 999) < 999: model.Add(sum(total_elec_interns_in_month) <= generic_elective_caps['max_interns'])
            if generic_elective_caps.get('min_seniors', 0) > 0: model.Add(sum(total_elec_seniors_in_month) >= generic_elective_caps['min_seniors'])
            if generic_elective_caps.get('max_seniors', 999) < 999: model.Add(sum(total_elec_seniors_in_month) <= generic_elective_caps['max_seniors'])

    # 3. Dynamic PGY Rules (Graduation limits)
    # Allows summing all specific mappings.
    for r, res_data in enumerate(residents):
        pgy = res_data['year_pgy']
        # Find matching rules
        applicable_rules = [pr for pr in pgy_rules if pr['pgy_level'] == pgy]
        for rule in applicable_rules:
            # Rule target could be 'Elective' (applies to all electives) or a specific rotation
            rule_rot_name = rule['rotation_name'].lower().strip()
            
            matched_indices = []
            for s, rot_data in enumerate(all_rotations):
                # If rule is 'Elective', perfectly capture anything tagged _is_elective
                if rule_rot_name == 'elective' and rot_data['_is_elective']:
                    matched_indices.append(s)
                elif rot_data['name'].lower() == rule_rot_name:
                    matched_indices.append(s)
                    
            if matched_indices:
                total_months = sum(shifts[(r, m, s)] for m in months for s in matched_indices)
                model.Add(total_months >= rule['min_months'])
                model.Add(total_months <= rule['max_months'])

    # 4. Forbidden Adjacencies
    # "ICU cannot touch Nights"
    for adj in adjacencies:
        rot1 = adj['rotation_1'].lower()
        rot2 = adj['rotation_2'].lower()
        
        idx1 = next((i for i, rot in enumerate(all_rotations) if rot['name'].lower() == rot1), None)
        idx2 = next((i for i, rot in enumerate(all_rotations) if rot['name'].lower() == rot2), None)
        
        if idx1 is not None and idx2 is not None:
            for r in resident_indices:
                for m in range(num_months - 1): # Compare m and m+1
                    # A -> not B
                    model.AddImplication(shifts[(r, m, idx1)], shifts[(r, m+1, idx2)].Not())
                    # B -> not A
                    model.AddImplication(shifts[(r, m, idx2)], shifts[(r, m+1, idx1)].Not())

    # 5. Hard Blocks
    for hb in hard_blocks:
        r_idx = next((i for i, res in enumerate(residents) if res['name'] == hb['resident_name']), None)
        m_idx = hb['month']
        s_idx = next((i for i, rot in enumerate(all_rotations) if rot['name'] == hb['rotation_name']), None)
        
        if r_idx is not None and s_idx is not None and 0 <= m_idx < num_months:
            model.Add(shifts[(r_idx, m_idx, s_idx)] == 1)

    # 6. Soft Requests (Objective function)
    obj_terms = []
    for req in requests:
        r_idx = next((i for i, res in enumerate(residents) if res['name'] == req['resident_name']), None)
        m_idx = req['month']
        # Request could be generic 'Elective' or 'elective-XYZ'
        # To handle generic requests safely, we should map them. But right now we map strict strings.
        s_idx = next((i for i, rot in enumerate(all_rotations) if rot['name'] == req['rotation_name']), None)
        
        if r_idx is not None and s_idx is not None and 0 <= m_idx < num_months:
            obj_terms.append(shifts[(r_idx, m_idx, s_idx)] * req['weight'])

    if obj_terms:
        model.Maximize(sum(obj_terms))

    # --- SOLVE ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        for r in resident_indices:
            row_data = {
                'Resident': residents[r]['name'],
                'Year': f"PGY-{residents[r]['year_pgy']}",
                'Level': 'Senior' if residents[r]['year_pgy'] >= 2 else 'Intern'
            }
            for m in months:
                for s in rotation_indices:
                    if solver.Value(shifts[(r, m, s)]):
                        row_data[month_names[m]] = all_rotations[s]['name']
            schedule_data.append(row_data)
            
        df = pd.DataFrame(schedule_data)
        return True, df, solver.StatusName(status)
    else:
        return False, None, solver.StatusName(status)
