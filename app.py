from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

BASE = Path(__file__).parent
DATA = BASE 

st.set_page_config(page_title="InsureIQ | Insurance Analytics", page_icon="🛡️", layout="wide")

# ---------- Styling ----------
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 2.4rem; max-width: 1500px;}
  [data-testid="stMetric"] {background: #111c2f; border: 1px solid #253650; padding: 16px 18px; border-radius: 14px;}
  [data-testid="stMetricLabel"] {color: #aabbd2;}
  [data-testid="stMetricValue"] {color: #f5f8ff;}
  .hero {padding: 22px 26px; border-radius: 18px; background: linear-gradient(115deg,#13233b,#1b3b5a); border: 1px solid #2b4968; margin-bottom: 18px;}
  .hero h1 {margin: 0; color: #f5f8ff; font-size: 2rem;}
  .hero p {margin: 7px 0 0; color: #c2d4e8;}
  .note {padding: 12px 15px; background: #202b3d; border-left: 4px solid #65b5d8; border-radius: 8px; color: #dce7f5;}
  h2, h3 {letter-spacing: -0.02em;}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    customers = pd.read_csv(DATA / "customers.csv")
    policies = pd.read_csv(DATA / "policies.csv", parse_dates=["start_date", "end_date"])
    claims = pd.read_csv(DATA / "claims.csv", parse_dates=["claim_date"])
    payments = pd.read_csv(DATA / "payments.csv", parse_dates=["payment_date"])
    return customers, policies, claims, payments

try:
    customers, policies, claims, payments = load_data()
except Exception as exc:
    st.error(f"Could not load the project CSV files. Keep the data folder beside app.py. Details: {exc}")
    st.stop()

# Filter choices are shared across views.
st.sidebar.markdown("## 🛡️ InsureIQ")
st.sidebar.caption("Insurance portfolio analytics")
st.sidebar.divider()
policy_types = sorted(policies["policy_type"].dropna().unique().tolist())
selected_types = st.sidebar.multiselect("Policy type", policy_types, default=policy_types)
policy_statuses = sorted(policies["status"].dropna().unique().tolist())
selected_statuses = st.sidebar.multiselect("Policy status", policy_statuses, default=policy_statuses)
cities = sorted(customers["city"].dropna().unique().tolist())
selected_cities = st.sidebar.multiselect("Customer city", cities, default=cities)

filtered_policies = policies[
    policies["policy_type"].isin(selected_types) & policies["status"].isin(selected_statuses)
].merge(customers[["customer_id", "full_name", "city", "age", "annual_income"]], on="customer_id", how="left")
filtered_policies = filtered_policies[filtered_policies["city"].isin(selected_cities)]
policy_ids = set(filtered_policies["policy_id"].tolist())
filtered_claims = claims[claims["policy_id"].isin(policy_ids)].copy()
filtered_payments = payments[payments["policy_id"].isin(policy_ids)].copy()
filtered_customers = customers[customers["customer_id"].isin(filtered_policies["customer_id"].unique())].copy()

# Aggregate claim/payment tables before joining to avoid multiplying values across one-to-many joins.
claims_by_policy = filtered_claims.groupby("policy_id", as_index=False).agg(
    claim_count=("claim_id", "count"), total_claim_amount=("claim_amount", "sum"),
    total_settlement=("settlement_amount", "sum")
)
payments_by_policy = filtered_payments[filtered_payments["status"].eq("PAID")].groupby("policy_id", as_index=False).agg(
    paid_amount=("amount", "sum"), paid_payment_count=("payment_id", "count")
)
portfolio = filtered_policies.merge(claims_by_policy, on="policy_id", how="left").merge(payments_by_policy, on="policy_id", how="left")
for col in ["claim_count", "total_claim_amount", "total_settlement", "paid_amount", "paid_payment_count"]:
    portfolio[col] = portfolio[col].fillna(0)
portfolio["loss_ratio"] = portfolio["total_settlement"] / portfolio["premium"].replace(0, pd.NA)
portfolio["profit_proxy"] = portfolio["paid_amount"] - portfolio["total_settlement"]
portfolio["claim_frequency"] = portfolio["claim_count"]

st.markdown("""
<div class="hero">
  <h1>🛡️ InsureIQ</h1>
  <p>Insurance portfolio intelligence · policy lifecycle · claims review · payment performance</p>
</div>
""", unsafe_allow_html=True)
st.caption("Project data: 4 related tables from the supplied workbook. Use the sidebar filters to explore the portfolio.")

# KPI row
k1, k2, k3, k4, k5 = st.columns(5)
policy_count = len(filtered_policies)
customer_count = filtered_customers["customer_id"].nunique()
total_premium = filtered_policies["premium"].sum()
settlements = filtered_claims["settlement_amount"].sum()
loss_ratio = settlements / total_premium if total_premium else 0
paid_total = filtered_payments.loc[filtered_payments["status"].eq("PAID"), "amount"].sum()
k1.metric("Customers", f"{customer_count:,}")
k2.metric("Policies", f"{policy_count:,}")
k3.metric("Policy premium total", f"₹{total_premium:,.0f}")
k4.metric("Settlements", f"₹{settlements:,.0f}")
k5.metric("Settlement / premium", f"{loss_ratio:.1%}")

view = st.tabs(["Overview", "Policies", "Claims & review", "Payments", "Customers", "Data quality & SQL"])

with view[0]:
    left, right = st.columns(2)
    with left:
        st.subheader("Portfolio by policy type")
        by_type = filtered_policies.groupby("policy_type", as_index=False).agg(
            policies=("policy_id", "count"), premium=("premium", "sum")
        )
        if not by_type.empty:
            fig = px.bar(by_type, x="policy_type", y="premium", color="policy_type", text_auto=".2s", title="Total policy premium")
            fig.update_layout(showlegend=False, xaxis_title="Policy type", yaxis_title="Premium (₹)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No policies match the current filters.")
    with right:
        st.subheader("Claim status mix")
        status_mix = filtered_claims["claim_status"].value_counts().rename_axis("claim_status").reset_index(name="claims")
        if not status_mix.empty:
            fig = px.pie(status_mix, names="claim_status", values="claims", hole=0.55, title="Claims by current status")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No claims match the current filters.")
    left, right = st.columns(2)
    with left:
        st.subheader("Monthly payment activity")
        if not filtered_payments.empty:
            monthly = filtered_payments.assign(month=filtered_payments["payment_date"].dt.to_period("M").dt.to_timestamp()).groupby(["month", "status"], as_index=False).agg(amount=("amount", "sum"))
            fig = px.line(monthly, x="month", y="amount", color="status", markers=True, title="Payment amount by month and status")
            fig.update_layout(xaxis_title="Month", yaxis_title="Amount (₹)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No payments match the current filters.")
    with right:
        st.subheader("Policy status")
        stat = filtered_policies["status"].value_counts().rename_axis("status").reset_index(name="policies")
        if not stat.empty:
            fig = px.bar(stat, x="status", y="policies", color="status", text_auto=True, title="Policies by lifecycle status")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No policies match the current filters.")
    st.markdown('<div class="note">Interpretation: the loss ratio shown here is total settlement amount divided by policy premium total for the selected portfolio. It is a simplified indicator, not a complete actuarial profitability measure.</div>', unsafe_allow_html=True)

with view[1]:
    st.subheader("Policy portfolio")
    summary = portfolio.groupby("policy_type", as_index=False).agg(
        policies=("policy_id", "count"), premium_total=("premium", "sum"),
        sum_assured_total=("sum_assured", "sum"), claims=("claim_count", "sum"),
        claim_amount=("total_claim_amount", "sum"), settlements=("total_settlement", "sum"),
        paid_payment_amount=("paid_amount", "sum"), profit_proxy=("profit_proxy", "sum")
    )
    summary["loss_ratio"] = summary["settlements"] / summary["premium_total"].replace(0, pd.NA)
    summary["loss_ratio"] = summary["loss_ratio"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.download_button("Download filtered policy table", filtered_policies.to_csv(index=False).encode("utf-8"), "filtered_policies.csv", "text/csv")
    st.subheader("Policy-level profitability proxy")
    display_profit = portfolio[["policy_id", "policy_type", "status", "premium", "paid_amount", "total_settlement", "profit_proxy"]].copy()
    display_profit = display_profit.sort_values("profit_proxy", ascending=False)
    st.dataframe(display_profit.head(100), use_container_width=True, hide_index=True)
    st.caption("Profit proxy = successful payment amount − settlement amount. This is not full profit because expenses, reserves and commissions are not included.")

with view[2]:
    st.subheader("Claims overview")
    a, b, c = st.columns(3)
    a.metric("Claims", f"{len(filtered_claims):,}")
    b.metric("Claim amount", f"₹{filtered_claims['claim_amount'].sum():,.0f}")
    c.metric("Settlement amount", f"₹{filtered_claims['settlement_amount'].sum():,.0f}")
    left, right = st.columns(2)
    with left:
        cs = filtered_claims["claim_status"].value_counts().rename_axis("claim_status").reset_index(name="count")
        if not cs.empty:
            st.plotly_chart(px.bar(cs, x="claim_status", y="count", color="claim_status", text_auto=True, title="Claims by status"), use_container_width=True)
    with right:
        if not filtered_claims.empty:
            by_date = filtered_claims.assign(month=filtered_claims["claim_date"].dt.to_period("M").dt.to_timestamp()).groupby("month", as_index=False).agg(claim_amount=("claim_amount", "sum"), claims=("claim_id", "count"))
            st.plotly_chart(px.line(by_date, x="month", y="claim_amount", markers=True, title="Claim amount trend"), use_container_width=True)
    st.subheader("Rule-based review queue")
    review = filtered_claims.copy()
    review["review_flag"] = "STANDARD"
    review.loc[review["claim_amount"] >= 300000, "review_flag"] = "HIGH CLAIM AMOUNT — REVIEW"
    review.loc[review["settlement_amount"] > review["claim_amount"], "review_flag"] = "SETTLEMENT EXCEEDS CLAIM — REVIEW"
    review = review[review["review_flag"].ne("STANDARD")].sort_values("claim_amount", ascending=False)
    st.dataframe(review, use_container_width=True, hide_index=True)
    st.download_button("Download review queue", review.to_csv(index=False).encode("utf-8"), "claim_review_queue.csv", "text/csv")
    st.caption("Review flags are simple rules for human review. They do not prove fraud and are not a trained fraud model.")

with view[3]:
    st.subheader("Payment performance")
    a, b, c = st.columns(3)
    a.metric("Payment attempts", f"{len(filtered_payments):,}")
    b.metric("Paid amount", f"₹{paid_total:,.0f}")
    fail = filtered_payments[filtered_payments["status"].eq("FAILED")]
    c.metric("Failed attempts", f"{len(fail):,}")
    if not filtered_payments.empty:
        month = filtered_payments.assign(month=filtered_payments["payment_date"].dt.to_period("M").dt.to_timestamp()).groupby(["month", "status"], as_index=False).agg(attempts=("payment_id", "count"), amount=("amount", "sum"))
        st.plotly_chart(px.bar(month, x="month", y="amount", color="status", barmode="group", title="Paid vs failed payment amount by month"), use_container_width=True)
        pay_summary = filtered_payments.groupby("status", as_index=False).agg(attempts=("payment_id", "count"), amount=("amount", "sum"))
        st.dataframe(pay_summary, use_container_width=True, hide_index=True)
    st.download_button("Download filtered payments", filtered_payments.to_csv(index=False).encode("utf-8"), "filtered_payments.csv", "text/csv")

with view[4]:
    st.subheader("Customer portfolio")
    customer_rollup = filtered_policies.groupby("customer_id", as_index=False).agg(
        policy_count=("policy_id", "count"), total_premium=("premium", "sum"),
        active_policies=("status", lambda s: (s == "ACTIVE").sum()),
        expired_policies=("status", lambda s: (s == "EXPIRED").sum()),
        lapsed_policies=("status", lambda s: (s == "LAPSED").sum())
    ).merge(customers, on="customer_id", how="left")
    if not customer_rollup.empty:
        st.dataframe(customer_rollup.sort_values("total_premium", ascending=False), use_container_width=True, hide_index=True)
        city = customer_rollup.groupby("city", as_index=False).agg(customers=("customer_id", "nunique"), premium=("total_premium", "sum"))
        st.plotly_chart(px.bar(city, x="city", y="premium", color="city", title="Policy premium by customer city", text_auto=".2s"), use_container_width=True)
        st.download_button("Download customer rollup", customer_rollup.to_csv(index=False).encode("utf-8"), "customer_portfolio.csv", "text/csv")
    else:
        st.info("No customers match the current filters.")

with view[5]:
    st.subheader("Data quality checks")
    data_map = {"customers": customers, "policies": policies, "claims": claims, "payments": payments}
    dq = []
    for name, frame in data_map.items():
        dq.append({"table": name, "rows": len(frame), "columns": len(frame.columns), "missing_cells": int(frame.isna().sum().sum()), "duplicate_rows": int(frame.duplicated().sum())})
    st.dataframe(pd.DataFrame(dq), use_container_width=True, hide_index=True)
    st.subheader("Relationship checks")
    checks = pd.DataFrame([
        {"check": "Policies with unknown customer", "count": int((~policies.customer_id.isin(customers.customer_id)).sum())},
        {"check": "Claims with unknown policy", "count": int((~claims.policy_id.isin(policies.policy_id)).sum())},
        {"check": "Payments with unknown policy", "count": int((~payments.policy_id.isin(policies.policy_id)).sum())},
        {"check": "Settlement exceeds claim amount", "count": int((claims.settlement_amount > claims.claim_amount).sum())},
    ])
    st.dataframe(checks, use_container_width=True, hide_index=True)
    st.subheader("Advanced SQL coverage")
    st.markdown("""
    - Normalized relational schema with primary and foreign keys
    - Aggregate KPIs using `GROUP BY`, `FILTER`, `COALESCE` and `NULLIF`
    - CTEs to aggregate claims and payments before joins
    - Window functions: running payment totals and profitability ranking
    - Rule-based claim review queue (not confirmed fraud)
    - Indexes for policy/customer and date-based access
    - Materialized view for reusable policy-type KPIs
    """)
    st.info("Open sql/insurance_analytics.sql for the full PostgreSQL query pack. Use the README for setup. The dashboard itself runs locally from the included CSV files and does not require PostgreSQL.")

st.sidebar.divider()
st.sidebar.caption("InsureIQ · Learning/demo project")
st.sidebar.caption("Amounts are shown in ₹ for readability; confirm the source dataset's currency before business use.")
