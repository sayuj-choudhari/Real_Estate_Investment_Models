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
    """
    T_HORIZON: The total years we are tracking wealth (e.g., 30).
    exit_at_t: If True, we sell the house at year t and move the equity to the S&P 500 for the remainder of T_HORIZON.
    """
    down_payment = 0.2 * P
    pmt, balances, interests = mortgage_calc(P, params['mortgage_rate'], params['mortgage_term'])
    
    wealth_buy_market = 0.0
    wealth_rent_market = down_payment 
    
    current_home_value = P
    current_rent_cost = params['rent']
    current_roommate_inc = params['roommate_rent']
    current_full_rent_inc = params['full_rent']
    basis = P * 1.01 

    # Simulation loop
    for year in range(1, T_HORIZON + 1):
        # 1. Appreciation
        if (exit_at_t and year <= t) or not exit_at_t:
            current_home_value *= (1 + params['home_appreciation'])
        
        idx = (year - 1) * 12
        interest_paid = interests[idx:idx+12].sum() if idx < len(interests) else 0
        balance_at_yr_end = balances[idx+11] if idx+11 < len(balances) else 0
        
        # 2. Tax Shield (Standard Deduction Floor)
        loan_cap_ratio = min(balance_at_yr_end, 750000) / balance_at_yr_end if balance_at_yr_end > 0 else 1
        adj_interest = interest_paid * loan_cap_ratio
        annual_prop_tax = (params['property_tax_rate'] * current_home_value) + params['mello_roos']
        
        total_itemized = adj_interest + annual_prop_tax
        deductible_amount = max(0, total_itemized - params['std_deduction'])
        tax_shield = deductible_amount * params['income_tax_rate']
        
        # 3. Income & Rent Logic
        # Case A: User still lives there
        if year <= t:
            income = current_roommate_inc * 0.98 
            net_rent_cost = current_rent_cost 
            maintenance = params['maintenance_rate'] * current_home_value
            gross_buy_cost = (12 * pmt) + annual_prop_tax + maintenance + params['hoa']
        # Case B: User has moved out
        else:
            net_rent_cost = 0 
            if exit_at_t:
                # Property was sold at end of year t. No more housing costs/income.
                income = 0
                gross_buy_cost = 0
                tax_shield = 0
            else:
                # Property kept as rental
                income = current_full_rent_inc * 0.95
                maintenance = params['maintenance_rate'] * current_home_value
                gross_buy_cost = (12 * pmt) + annual_prop_tax + maintenance + params['hoa']
            
        net_buy_cost = gross_buy_cost - tax_shield - income
        
        # 4. Wealth Compounding
        wealth_buy_market *= (1 + params['investment_return'])
        wealth_rent_market *= (1 + params['investment_return'])
        
        diff = net_buy_cost - net_rent_cost
        if diff > 0: wealth_rent_market += diff
        else: wealth_buy_market += abs(diff)

        # 5. Handle the "Flash Sale" at year t
        if exit_at_t and year == t:
            sales_costs = current_home_value * params['sell_cost_rate']
            net_proceeds = current_home_value - sales_costs
            taxable_gain = max(0, net_proceeds - basis)
            # SEC 121 EXCLUSION: If sold at year t, you likely qualify for $250k tax-free
            taxable_gain = max(0, taxable_gain - 250000)
            exit_tax = taxable_gain * 0.243
            
            # Liquidate equity into the market for the remaining years
            equity_into_market = net_proceeds - balance_at_yr_end - exit_tax
            wealth_buy_market += equity_into_market

        # 6. Inflationary Growth
        current_roommate_inc *= (1 + params['rent_growth'])
        current_full_rent_inc *= (1 + params['rent_growth'])
        if year <= t: current_rent_cost *= (1 + params['rent_growth'])

    # 7. FINAL LIQUIDATION (for the non-exit case)
    if not exit_at_t:
        sales_costs = current_home_value * params['sell_cost_rate']
        net_proceeds = current_home_value - sales_costs
        taxable_gain = max(0, net_proceeds - basis)
        # Loss of Sec 121 exclusion because it's been a rental for >3 years
        exit_tax = taxable_gain * 0.243
        home_equity = net_proceeds - balances[-1] - exit_tax
        wealth_buy_market += home_equity
    
    return wealth_buy_market - wealth_rent_market

# --- UI ---
st.title("🏡 The 'Quant' Irvine Buy-vs-Rent Model")
st.markdown("Comparing **Holding as Rental** vs **Selling Immediately** after moving out.")

with st.sidebar:
    st.header("📉 Market Macro")
    h_app = st.slider("Annual Appreciation (%)", 0.0, 10.0, 5.0) / 100
    r_gro = st.slider("Rental Growth Rate (%)", 0.0, 8.0, 3.5) / 100
    i_ret = st.slider("S&P 500 Return (%)", 0.0, 15.0, 9.0) / 100
    
    st.header("🏠 Property Specifics")
    m_rate = st.slider("Mortgage Rate (%)", 0.0, 10.0, 6.7) / 100
    hoa_yr = st.number_input("Annual HOA/Insurance ($)", value=7200)
    mello = st.number_input("Annual Mello-Roos ($)", value=4000)
    roomie = st.number_input("Initial Roommate Income ($)", value=23400)
    full_r = st.number_input("Initial Full Rental Income ($)", value=54000)
    curr_rent = st.number_input("Renter's Annual Rent ($)", value=42000)

params = {
    'home_appreciation': h_app, 'rent_growth': r_gro, 'investment_return': i_ret,
    'mortgage_rate': m_rate, 'mortgage_term': 30, 'property_tax_rate': 0.012,
    'mello_roos': mello, 'maintenance_rate': 0.01, 'hoa': hoa_yr, 'sell_cost_rate': 0.06,
    'income_tax_rate': 0.35, 'std_deduction': 15000, 'rent': curr_rent,
    'roommate_rent': roomie, 'full_rent': full_r
}

if st.button("🚀 EXECUTE DUAL-STRATEGY ANALYSIS"):
    t_vals = list(range(1, 11))
    prices_hold = []
    prices_sell = []
    
    with st.spinner("Analyzing exit strategies..."):
        for t in t_vals:
            # Case 1: Keep as rental until year 30
            try:
                p_h = bisect(lambda P: simulate_housing_comparison_metric(P, t, 30, params, False), 0, 6000000, xtol=500)
                prices_hold.append(p_h)
            except: prices_hold.append(None)
            
            # Case 2: Sell at year t
            try:
                p_s = bisect(lambda P: simulate_housing_comparison_metric(P, t, 30, params, True), 0, 6000000, xtol=500)
                prices_sell.append(p_s)
            except: prices_sell.append(None)

    df = pd.DataFrame({
        "Years as Resident": t_vals, 
        "Max Price (Hold 30Y)": prices_hold,
        "Max Price (Sell at Year t)": prices_sell
    })
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Price Comparison")
        st.dataframe(df.style.format({"Max Price (Hold 30Y)": "${:,.0f}", "Max Price (Sell at Year t)": "${:,.0f}"}), hide_index=True)
    with c2:
        st.subheader("The Strategy Gap")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df["Years as Resident"], df["Max Price (Hold 30Y)"], label="Keep as Rental", color='#1E88E5', marker='o')
        ax.plot(df["Years as Resident"], df["Max Price (Sell at Year t)"], label="Sell Immediately", color='#E63946', marker='s')
        ax.set_ylabel("Max Purchase Price ($)")
        ax.set_xlabel("Years Lived in Property")
        ax.legend()
        ax.grid(True, alpha=0.2)
        st.pyplot(fig)

st.info("💡 **Insight:** Notice the 'Sell Immediately' price is usually lower for early years. This represents the 'Transaction Friction' of the 6% agent fee and closing costs. If the red line is below current market prices, a short-term buy is a guaranteed loss.")