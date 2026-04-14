from ortools.sat.python import cp_model
import pandas as pd

# Objective weights
REQUEST_WEIGHT = 2   # multiplier on soft-request satisfaction
STRESS_WEIGHT  = 1   # multiplier on cumulative-stress penalty (2:1 ratio)

def generate_schedule(residents, rotations, electives, pgy_rules, requests, hard_blocks, adjacencies):
    if not residents or not rotations:
        return False, None, "Must have at least one resident and one rotation."

    num_months = 12
    months = range(num_months)
    month_names = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]

    # --- Build Rotation Index ---
    all_rotations = []
    for rot in rotations:
        r_copy = dict(rot)
        r_copy['_is_elective'] = (r_copy['name'].lower() == 'elective')
        r_copy.setdefault('stress', 5)
        all_rotations.append(r_copy)

    for elec in electives:
        all_rotations.append({
            'name': f"elective-{elec['name']}",
            'min_total': 0, 'max_total': 999,
            'min_interns': 0, 'max_interns': 999,
            'min_seniors': 0, 'max_seniors': 999,
            '_is_elective': True,
            'stress': 0,   # electives are zero-stress by definition
        })

    rotation_indices = range(len(all_rotations))
    resident_indices = range(len(residents))

    model = cp_model.CpModel()

    # Variables: shifts[(r, m, s)] = 1 iff resident r is on rotation s in month m
    shifts = {}
    for r in resident_indices:
        for m in months:
            for s in rotation_indices:
                shifts[(r, m, s)] = model.NewBoolVar(f'shift_r{r}_m{m}_s{s}')

    # ── Constraints ──────────────────────────────────────────────────────────

    # 1. One rotation per resident per month
    for r in resident_indices:
        for m in months:
            model.AddExactlyOne(shifts[(r, m, s)] for s in rotation_indices)

    # 2. Coverage Quotas
    generic_elective_caps = next((rot for rot in rotations if rot['name'].lower() == 'elective'), None)

    for m in months:
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

            if rot_data['_is_elective']:
                total_electives_in_month.extend(r_in_rot)
                total_elec_interns_in_month.extend(int_in_rot)
                total_elec_seniors_in_month.extend(sen_in_rot)

            if rot_data['name'].lower() != 'elective':
                if rot_data.get('min_total', 0) > 0:   model.Add(sum(r_in_rot) >= rot_data['min_total'])
                if rot_data.get('max_total', 999) < 999: model.Add(sum(r_in_rot) <= rot_data['max_total'])
                if rot_data.get('min_interns', 0) > 0:  model.Add(sum(int_in_rot) >= rot_data['min_interns'])
                if rot_data.get('max_interns', 999) < 999: model.Add(sum(int_in_rot) <= rot_data['max_interns'])
                if rot_data.get('min_seniors', 0) > 0:  model.Add(sum(sen_in_rot) >= rot_data['min_seniors'])
                if rot_data.get('max_seniors', 999) < 999: model.Add(sum(sen_in_rot) <= rot_data['max_seniors'])

        if generic_elective_caps:
            if generic_elective_caps.get('min_total', 0) > 0:   model.Add(sum(total_electives_in_month) >= generic_elective_caps['min_total'])
            if generic_elective_caps.get('max_total', 999) < 999: model.Add(sum(total_electives_in_month) <= generic_elective_caps['max_total'])
            if generic_elective_caps.get('min_interns', 0) > 0:  model.Add(sum(total_elec_interns_in_month) >= generic_elective_caps['min_interns'])
            if generic_elective_caps.get('max_interns', 999) < 999: model.Add(sum(total_elec_interns_in_month) <= generic_elective_caps['max_interns'])
            if generic_elective_caps.get('min_seniors', 0) > 0:  model.Add(sum(total_elec_seniors_in_month) >= generic_elective_caps['min_seniors'])
            if generic_elective_caps.get('max_seniors', 999) < 999: model.Add(sum(total_elec_seniors_in_month) <= generic_elective_caps['max_seniors'])

    # 3. PGY Rules
    for r, res_data in enumerate(residents):
        pgy = res_data['year_pgy']
        applicable_rules = [pr for pr in pgy_rules if pr['pgy_level'] == pgy]
        for rule in applicable_rules:
            rule_rot_name = rule['rotation_name'].lower().strip()
            matched_indices = []
            for s, rot_data in enumerate(all_rotations):
                if rule_rot_name == 'elective' and rot_data['_is_elective']:
                    matched_indices.append(s)
                elif rot_data['name'].lower() == rule_rot_name:
                    matched_indices.append(s)
            if matched_indices:
                total_months = sum(shifts[(r, m, s)] for m in months for s in matched_indices)
                model.Add(total_months >= rule['min_months'])
                model.Add(total_months <= rule['max_months'])

    # 4. Forbidden Adjacencies
    for adj in adjacencies:
        rot1 = adj['rotation_1'].lower()
        rot2 = adj['rotation_2'].lower()
        idx1 = next((i for i, rot in enumerate(all_rotations) if rot['name'].lower() == rot1), None)
        idx2 = next((i for i, rot in enumerate(all_rotations) if rot['name'].lower() == rot2), None)
        if idx1 is not None and idx2 is not None:
            for r in resident_indices:
                for m in range(num_months - 1):
                    model.AddImplication(shifts[(r, m, idx1)], shifts[(r, m+1, idx2)].Not())
                    model.AddImplication(shifts[(r, m, idx2)], shifts[(r, m+1, idx1)].Not())

    # 5. Hard Blocks
    for hb in hard_blocks:
        r_idx = next((i for i, res in enumerate(residents) if res['name'] == hb['resident_name']), None)
        m_idx = hb['month']
        s_idx = next((i for i, rot in enumerate(all_rotations) if rot['name'] == hb['rotation_name']), None)
        if r_idx is not None and s_idx is not None and 0 <= m_idx < num_months:
            model.Add(shifts[(r_idx, m_idx, s_idx)] == 1)

    # ── Objective ────────────────────────────────────────────────────────────
    # Build a lookup: rotation_index -> stress score
    stress_by_index = {s: int(all_rotations[s].get('stress', 5) or 5)
                       for s in rotation_indices}

    # ── Cumulative-stress auxiliary variables ─────────────────────────────────
    # cum_stress[r][m] = running cumulative stress at end of month m for resident r
    # Reset rule: if month m is an elective, cum_stress[r][m] = 0.
    # Otherwise: cum_stress[r][m] = cum_stress[r][m-1] + monthly_stress[r][m]
    #
    # We model this with:
    #   monthly_stress[r][m]   = Σ_s  stress_by_index[s] * shifts[r,m,s]  (integer, 0..10)
    #   on_elective[r][m]      = Σ_s  shifts[r,m,s]  for elective rotations (bool)
    #   cum_stress[r][m]       = (1 - on_elective[r][m]) * (cum_stress[r][m-1] + monthly_stress[r][m])
    #
    # Because multiplication of two variables is nonlinear, we use the
    # big-M / indicator approach supported by CP-SAT:
    #   If on_elective[r][m] == 1  →  cum_stress[r][m] = 0
    #   If on_elective[r][m] == 0  →  cum_stress[r][m] = cum_stress[r][m-1] + monthly_stress[r][m]

    MAX_CUM_STRESS = 10 * num_months  # upper bound (never exceeds 120)

    monthly_stress = {}   # integer variable per (r, m)
    on_elective    = {}   # bool variable per (r, m) — is this month an elective?
    cum_stress     = {}   # integer variable per (r, m)

    elective_indices = [s for s, rot in enumerate(all_rotations) if rot['_is_elective']]

    for r in resident_indices:
        for m in months:
            # Monthly stress = weighted sum of chosen rotation
            ms = model.NewIntVar(0, 10, f'ms_r{r}_m{m}')
            model.Add(ms == sum(stress_by_index[s] * shifts[(r, m, s)] for s in rotation_indices))
            monthly_stress[(r, m)] = ms

            # Is this month an elective?
            elec_var = model.NewBoolVar(f'elec_r{r}_m{m}')
            model.Add(sum(shifts[(r, m, s)] for s in elective_indices) == 1).OnlyEnforceIf(elec_var)
            model.Add(sum(shifts[(r, m, s)] for s in elective_indices) == 0).OnlyEnforceIf(elec_var.Not())
            on_elective[(r, m)] = elec_var

            # Cumulative stress with reset
            cs = model.NewIntVar(0, MAX_CUM_STRESS, f'cs_r{r}_m{m}')
            cum_stress[(r, m)] = cs

            prev_cs = cum_stress[(r, m-1)] if m > 0 else model.NewConstant(0)

            # If on elective → cs = 0
            model.Add(cs == 0).OnlyEnforceIf(elec_var)
            # If NOT on elective → cs = prev_cs + ms
            model.Add(cs == prev_cs + ms).OnlyEnforceIf(elec_var.Not())

    # ── Build combined objective ──────────────────────────────────────────────
    obj_terms = []

    # 1. Soft request satisfaction (weight ×2)
    for req in requests:
        r_idx = next((i for i, res in enumerate(residents) if res['name'] == req['resident_name']), None)
        m_idx = req['month']
        s_idx = next((i for i, rot in enumerate(all_rotations) if rot['name'] == req['rotation_name']), None)
        if r_idx is not None and s_idx is not None and 0 <= m_idx < num_months:
            obj_terms.append(REQUEST_WEIGHT * req['weight'] * shifts[(r_idx, m_idx, s_idx)])

    # 2. Cumulative stress minimization (weight ×1, subtracted)
    for r in resident_indices:
        for m in months:
            obj_terms.append(-STRESS_WEIGHT * cum_stress[(r, m)])

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
