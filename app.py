import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import bisect

# --- Page Configuration ---
st.set_page_config(page_title="Institutional OC Housing Model", layout="wide")

# --- Financial Logic ---
def mortgage_calc(P, r, term, down=0.2):
    loan = P * (1 - down)
    n = int(term * 12)
    r_m = r / 12
    pmt = (loan * r_m / (1 - (1 + r_m)**(-n))) if r_m > 0 else (loan / n)
    
    balances, interests = [], []
    balance = loan
    for _ in range(n):
        interest = balance * r_m
        principal = pmt - interest
        balance -= principal
        balances.append(max(0, balance))
        interests.append(interest)
    return pmt, np.array(balances), np.array(interests)

def simulate_housing_comparison_metric(P, t, T_HORIZON, params, exit_at_t=False):
    down_payment = 0.2 * P
    pmt, balances, interests = mortgage_calc(P, params['mortgage_rate'], params['mortgage_term'])
    
    wealth_buy_market = 0.0
    wealth_rent_market = down_payment 
    
    current_home_value = P
    current_rent_cost = params['rent']
    current_roommate_inc = params['roommate_rent']
    current_full_rent_inc = params['full_rent']
    
    # Basis and Depreciation Logic
    # In OC, land is ~70% of value. Only the building (30%) depreciates over 27.5 years.
    building_value = P * 0.30 
    annual_depreciation = building_value / 27.5
    accumulated_depreciation = 0
    basis = P * 1.01 # Purchase price + closing costs

    for year in range(1, T_HORIZON + 1):
        if (exit_at_t and year <= t) or not exit_at_t:
            current_home_value *= (1 + params['home_appreciation'])
        
        idx = (year - 1) * 12
        interest_paid = interests[idx:idx+12].sum() if idx < len(interests) else 0
        balance_at_yr_end = balances[idx+11] if idx+11 < len(balances) else 0
        
        # 1. Tax Shield
        loan_cap_ratio = min(balance_at_yr_end, 750000) / balance_at_yr_end if balance_at_yr_end > 0 else 1
        adj_interest = interest_paid * loan_cap_ratio
        annual_prop_tax = (params['property_tax_rate'] * current_home_value) + params['mello_roos']
        
        # 2. Income & Maintenance
        if year <= t:
            income = current_roommate_inc * 0.98 
            mgmt_fee = 0 # Self-managed while living there
            net_rent_cost = current_rent_cost 
        else:
            if exit_at_t:
                income, mgmt_fee, net_rent_cost = 0, 0, 0
            else: