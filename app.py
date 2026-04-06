import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import bisect

# --- Page Configuration ---
st.set_page_config(
    page_title="OC Housing Break-Even Model",
    page_icon="🏡",
    layout="wide"
)

# --- Financial Logic ---
def mortgage_calc(P, r, term, down=0.2):
    loan = P * (1 - down)
    n = int(term * 12)
    r_m = r / 12
    if r_m > 0:
        pmt = loan * r_m / (1 - (1 + r_m)**(-n))
    else:
        pmt = loan / n
        
    balances, interests = [], []
    balance = loan
    for _ in range(n):
        interest = balance * r_m
        principal = pmt - interest
        balance -= principal
        balances.append(max(0, balance))
        interests.append(interest)
    return pmt, np.array(balances), np.array(interests)

def simulate_housing_comparison_metric(P, t, T_TOTAL, params):
    down_payment = 0.2 * P
    pmt, balances, interests = mortgage_calc(P, params['mortgage_rate'], params['mortgage_term'])
    
    # Buy scenario: Starts with 0 liquid, all in down payment
    # Rent scenario: Starts with down payment amount invested in market
    wealth_buy_market = 0.0
    wealth_rent_market = down_payment
    
    current_home_value = P
    current_rent_cost = params['rent']

    for year in range(1, T_TOTAL + 1):
        current_home_value *= (1 + params['home_appreciation'])
        idx = (year - 1) * 12
        interest_paid = interests[idx:idx+12].sum()
        balance_at_year_end = balances[idx+11] if idx+11 < len(balances) else 0
        
        # Tax Shield Calculation (Standard Deduction vs Itemized)
        # Simplified: Interest on first $750k + Prop Tax
        loan_cap = 750000
        deductible_fraction = min(balance_at_year_end, loan_cap) / balance_at_year_end if balance_at_year_end > 0 else 1
        deductible_interest = interest_paid * deductible_fraction
        annual_prop_tax = params['property_tax'] * current_home_value
        
        tax_shield = (deductible_interest + annual_prop_tax) * params['income_tax_rate']
        
        # Expenses
        maintenance = params['maintenance'] * current_home_value
        gross_buy_cost = (12 * pmt) + annual_prop_tax + maintenance + params['hoa']
        
        # Income Logic
        if year <= t:
            income = params['roommate_rent'] * 0.98 # 2% vacancy
        else:
            income = params['full_rent'] * 0.95 # 5% vacancy
            
        net_buy_cost = gross_buy_cost - tax_shield - income
        
        # Rent logic: If living there (year <= t), pay rent in rent scenario
        # If year > t, user has moved out, rent cost is 0 (assumed moving elsewhere)
        net_rent_cost = current_rent_cost if year <= t else 0
        if year <= t:
            current_rent_cost *= (1 + params['rent_growth'])
        
        # Market Growth
        wealth_buy_market *= (1 + params['investment_return'])
        wealth_rent_market *= (1 + params['investment_return'])
        
        # Monthly savings/deficit reinvestment
        diff = net_buy_cost - net_rent_cost
        if diff > 0:
            # Buying is more expensive; renter invests the difference
            wealth_rent_market += diff
        else:
            # Renting is more expensive; buyer invests the savings
            wealth_buy_market += abs(diff)

    # Final Liquidation
    rem_loan = balances[min(T_TOTAL*12-1, len(balances)-1)]
    selling_fees = current_home_value * params['sell_cost']
    home_equity = current_home_value - rem_loan - selling_fees
    
    total_buy_wealth = home_equity + wealth_buy_market
    return total_buy_wealth - wealth_rent_market

# --- Streamlit UI ---
st.title("🏡 Orange County Real Estate Break-Even Model")
st.markdown("""
This tool calculates the **maximum purchase price** for a property in Irvine/Newport Beach 
where buying and eventually renting out the property outperforms renting and investing in the S&P 500.
""")

with st.sidebar:
    st.header("📊 Market Assumptions")
    h_app = st.slider("Annual Appreciation (%)", 0.0, 15.0, 6.0) / 100
    i_ret = st.slider("S&P 500 Annual Return (%)", 0.0, 15.0, 10.0) / 100
    m_rate = st.slider("Mortgage Interest Rate (%)", 0.0, 10.0, 6.7) / 100
    
    st.header("💸 Costs & Income")
    curr_rent = st.number_input("Current Annual Rent ($)", value=42000)
    roomie_inc = st.number_input("Annual Roommate Income ($)", value=23400)
    future_rent = st.number_input("Future Total Annual Rental Income ($)", value=48000)
    hoa = st.number_input("Annual HOA/Insurance ($)", value=7200)

params = {
    'home_appreciation': h_app,
    'investment_return': i_ret,
    'mortgage_rate': m_rate,
    'mortgage_term': 30,
    'property_tax': 0.012,
    'maintenance': 0.01,
    'hoa': hoa,
    'sell_cost': 0.06,
    'rent': curr_rent,
    'rent_growth': 0.035,
    'roommate_rent': roomie_inc,
    'full_rent': future_rent,
    'income_tax_rate': 0.35
}

# --- Execution ---
if st.button("Calculate Investment Thresholds"):
    t_vals = list(range(1, 11))
    prices = []
    
    with st.spinner("Optimizing break-even prices..."):
        for t in t_vals:
            try:
                # Using bisection method to find the Price P where delta wealth = 0
                sol = bisect(lambda P: simulate_housing_comparison_metric(P, t, 30, params), 
                             200_000, 5_000_000, xtol=500)
                prices.append(sol)
            except ValueError:
                prices.append(None)

    # --- Display Results ---
    df = pd.DataFrame({
        "Years Living in Property": t_vals,
        "Max Purchase Price": prices
    })

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Analysis Table")
        st.write("If you pay *less* than the price below, Buying wins.")
        st.dataframe(
            df.style.format({"Max Purchase Price": "${:,.0f}"}),
            hide_index=True
        )

    with col2:
        st.subheader("The Break-Even Curve")
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(df["Years Living in Property"], df["Max Purchase Price"], 
                marker='o', linestyle='-', color='#1E88E5', linewidth=2)
        ax.set_xlabel("Years Lived as Primary Resident")
        ax.set_ylabel("Max Purchase Price ($)")
        ax.grid(True, linestyle='--', alpha=0.7)
        st.pyplot(fig)

st.info("💡 Note: This model assumes a 30-year total horizon and standard CA property tax rates.")