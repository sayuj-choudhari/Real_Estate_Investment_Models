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
                income = current_full_rent_inc * 0.95
                mgmt_fee = income * params['mgmt_rate'] # Professional Management
                net_rent_cost = 0 
                # Track depreciation only during rental years
                accumulated_depreciation += annual_depreciation

        # 3. Expenses
        maintenance = params['maintenance_rate'] * current_home_value
        if exit_at_t and year > t:
            gross_buy_cost = 0
            tax_shield = 0
        else:
            total_itemized = adj_interest + annual_prop_tax
            deductible_amount = max(0, total_itemized - params['std_deduction'])
            tax_shield = deductible_amount * params['income_tax_rate']
            gross_buy_cost = (12 * pmt) + annual_prop_tax + maintenance + params['hoa'] + mgmt_fee
            
        # 4. Wealth Delta
        wealth_buy_market *= (1 + params['investment_return'])
        wealth_rent_market *= (1 + params['investment_return'])
        
        diff = gross_buy_cost - tax_shield - income - net_rent_cost
        if diff > 0: wealth_rent_market += diff
        else: wealth_buy_market += abs(diff)

        # 5. The Exit at Year T
        if exit_at_t and year == t:
            sales_costs = current_home_value * params['sell_cost_rate']
            net_proceeds = current_home_value - sales_costs
            taxable_gain = max(0, net_proceeds - basis)
            # Qualifies for Sec 121
            taxable_gain = max(0, taxable_gain - 250000)
            exit_tax = taxable_gain * 0.243
            wealth_buy_market += (net_proceeds - balance_at_yr_end - exit_tax)

        # Growth
        current_roommate_inc *= (1 + params['rent_growth'])
        current_full_rent_inc *= (1 + params['rent_growth'])
        if year <= t: current_rent_cost *= (1 + params['rent_growth'])

    # 6. Final Liquidation (Non-Exit Case)
    if not exit_at_t:
        sales_costs = current_home_value * params['sell_cost_rate']
        net_proceeds = current_home_value - sales_costs
        
        # Depreciation Recapture Tax (25% on accumulated depreciation)
        recapture_tax = accumulated_depreciation * 0.25
        
        # Capital Gains on remaining profit
        taxable_gain = max(0, net_proceeds - (basis - accumulated_depreciation))
        cap_gains_tax = taxable_gain * 0.243
        
        home_equity = net_proceeds - balances[-1] - recapture_tax - cap_gains_tax
        wealth_buy_market += home_equity
    
    return wealth_buy_market - wealth_rent_market

# --- UI ---
st.title("🏡 Institutional OC Housing Decision Engine")
st.markdown("Stress-tested for **Depreciation Recapture**, **Management Fees**, and **Standard Deduction Floors**.")

with st.sidebar:
    st.header("📈 Macro Assumptions")
    h_app = st.slider("Home Appreciation (%)", 0.0, 10.0, 4.5) / 100
    r_gro = st.slider("Rental Growth Rate (%)", 0.0, 8.0, 3.5) / 100
    i_ret = st.slider("S&P 500 Return (%)", 0.0, 15.0, 9.5) / 100
    
    st.header("🛠️ Operating Costs")
    maint_rate = st.slider("Maintenance Rate (%)", 0.5, 3.0, 1.5) / 100
    mgmt_rate = st.slider("Property Management (%)", 0, 12, 10) / 100
    m_rate = st.slider("Mortgage Rate (%)", 0.0, 10.0, 6.75) / 100
    
    st.header("📍 Property Details")
    hoa_yr = st.number_input("Annual HOA/Insurance ($)", value=8400)
    mello = st.number_input("Annual Mello-Roos ($)", value=4500)
    curr_rent = st.number_input("Renter's Current Annual Rent ($)", value=45000)
    roomie = st.number_input("Initial Roommate Income ($)", value=24000)
    full_r = st.number_input("Initial Full Rental Income ($)", value=56000)

params = {
    'home_appreciation': h_app, 'rent_growth': r_gro, 'investment_return': i_ret,
    'mortgage_rate': m_rate, 'mortgage_term': 30, 'property_tax_rate': 0.012,
    'mello_roos': mello, 'maintenance_rate': maint_rate, 'mgmt_rate': mgmt_rate,
    'hoa': hoa_yr, 'sell_cost_rate': 0.06, 'income_tax_rate': 0.35, 
    'std_deduction': 15000, 'rent': curr_rent, 'roommate_rent': roomie, 'full_rent': full_r
}

if st.button("🚀 CALCULATE ADJUSTED BREAK-EVEN"):
    t_vals = list(range(1, 11))
    prices_hold, prices_sell = [], []
    
    for t in t_vals:
        try:
            p_h = bisect(lambda P: simulate_housing_comparison_metric(P, t, 30, params, False), 100000, 6000000, xtol=500)
            prices_hold.append(p_h)
        except: prices_hold.append(None)
        try:
            p_s = bisect(lambda P: simulate_housing_comparison_metric(P, t, 30, params, True), 100000, 6000000, xtol=500)
            prices_sell.append(p_s)
        except: prices_sell.append(None)

    df = pd.DataFrame({"Years": t_vals, "Hold 30Y": prices_hold, "Sell at T": prices_sell})
    c1, c2 = st.columns([1, 2])
    with c1:
        st.dataframe(df.style.format({"Hold 30Y": "${:,.0f}", "Sell at T": "${:,.0f}"}), hide_index=True)
    with c2:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df["Years"], df["Hold 30Y"], label="Hold as Rental (Recapture Adjusted)", color='#1E88E5', marker='o')
        ax.plot(df["Years"], df["Sell at T"], label="Sell Immediately (Friction Adjusted)", color='#E63946', marker='s')
        ax.set_ylabel("Max Purchase Price ($)")
        ax.legend()
        st.pyplot(fig)

st.error("🚨 CRITICAL: If the blue line (Hold) is dropping significantly, the 10% Management Fee and Depreciation Recapture are outweighing the rental income gains.")