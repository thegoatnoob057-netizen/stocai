import streamlit as st
import yfinance as yf
import pandas as pd
import requests

st.set_page_config(page_title="StocAI | Smart NSE & BSE Stock Classifier", page_icon="🤖", layout="centered")

st.markdown("""
<style>
.top-badge { background-color: #064E3B; color: #6EE7B7; padding: 15px; border-radius: 10px; border-left: 5px solid #10B981; font-size: 16px; font-weight: bold; margin-bottom: 14px; }
.risky-badge { background-color: #7F1D1D; color: #FCA5A5; padding: 15px; border-radius: 10px; border-left: 5px solid #EF4444; font-size: 16px; font-weight: bold; margin-bottom: 14px; }
.neutral-badge { background-color: #1E293B; color: #CBD5E1; padding: 15px; border-radius: 10px; border-left: 5px solid #64748B; font-size: 16px; font-weight: bold; margin-bottom: 14px; }
.disclaimer-box { background-color: #2A2416; padding: 12px; border-radius: 8px; border: 1px solid #F59E0B; font-size: 12px; color: #FCD34D; margin-top: 30px; }
</style>
""", unsafe_allow_html=True)

if "checks_used" not in st.session_state:
    st.session_state.checks_used = 0

FREE_LIMIT = 3

KNOWN_ALIASES = {
    "ZOMATO": "ETERNAL",
    "PAYTM": "PAYTM",
    "TATA MOTORS": "TATAMOTORS",
    "TATA STEEL": "TATASTEEL",
    "TATA POWER": "TATAPOWER",
    "HDFC": "HDFCBANK",
    "HDFC BANK": "HDFCBANK",
    "ICICI": "ICICIBANK",
    "ICICI BANK": "ICICIBANK",
    "SBI": "SBIN",
    "STATE BANK": "SBIN",
    "AIRTEL": "BHARTIARTL",
    "BHARTI AIRTEL": "BHARTIARTL",
    "BAJAJ FINANCE": "BAJFINANCE",
    "MARUTI SUZUKI": "MARUTI",
    "SUN PHARMA": "SUNPHARMA",
    "MAHINDRA": "M&M",
    "KOTAK": "KOTAKBANK",
    "AXIS": "AXISBANK",
    "ADANI": "ADANIENT",
    "JIO": "JIOFIN"
}

@st.cache_data(ttl=3600)
def resolve_indian_ticker(user_query, prefer_nse=True):
    cleaned = user_query.strip().upper().replace(".NS", "").replace(".BO", "")
    if cleaned in KNOWN_ALIASES:
        cleaned = KNOWN_ALIASES[cleaned]
    preferred_ext = ".NS" if prefer_nse else ".BO"
    secondary_ext = ".BO" if prefer_nse else ".NS"
    direct_symbol = cleaned.replace(" ", "")
    for ext in [preferred_ext, secondary_ext]:
        candidate = direct_symbol + ext
        if not yf.Ticker(candidate).history(period="5d").empty:
            return candidate, direct_symbol
    try:
        url = "https://yahoo.com" + requests.utils.quote(user_query) + "&quotesCount=8&newsCount=0"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if resp.status_code == 200:
            for ext in [preferred_ext, secondary_ext]:
                for q in resp.json().get("quotes", []):
                    sym = q.get("symbol", "")
                    if sym.endswith(ext):
                        return sym, sym.replace(".NS", "").replace(".BO", "")
    except Exception:
        pass
    return direct_symbol + preferred_ext, direct_symbol

@st.cache_data(ttl=180)
def fetch_live_nse_quote(symbol):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://nseindia.com" + symbol
    }
    try:
        s = requests.Session()
        s.get("https://nseindia.com", headers=headers, timeout=5)
        r = s.get("https://nseindia.com/api/quote-equity?symbol=" + symbol, headers=headers, timeout=5)
        if r.status_code == 200:
            d = r.json()
            p = d.get("priceInfo", {})
            if p.get("lastPrice") is not None:
                return {
                    "live_price": float(p["lastPrice"]),
                    "day_change_pct": float(p["pChange"]) if p.get("pChange") is not None else None,
                    "company_name": d.get("info", {}).get("companyName", symbol),
                    "source": "NSE India Direct Feed"
                }
    except Exception:
        pass
    return None

@st.cache_data(ttl=300)
def fetch_stock_history(full_ticker):
    stock = yf.Ticker(full_ticker)
    hist = stock.history(period="3mo")
    try:
        name = stock.info.get("shortName") or stock.info.get("longName") or full_ticker
    except Exception:
        name = full_ticker
    return hist, name

def classify_stock(live_price, hist, lookback_days, live_day_pct=None):
    actual_lookback = min(lookback_days, len(hist) - 1)
    if actual_lookback == 1 and live_day_pct is not None:
        pct_change = live_day_pct
    else:
        past_price = float(hist["Close"].iloc[-(actual_lookback + 1)])
        pct_change = ((live_price - past_price) / past_price) * 100

    recent_returns = hist["Close"].pct_change().dropna().tail(30) * 100
    std_dev = float(recent_returns.std()) if len(recent_returns) >= 2 else 0.0

    if std_dev <= 1.5:
        cons = "Consistent"
        note = f"Steady Movement: Daily return deviation is low ({std_dev:.2f}%), showing consistent price behavior."
    elif std_dev <= 2.5:
        cons = "Moderate"
        note = f"Moderate Volatility: Daily return deviation is {std_dev:.2f}%."
    else:
        cons = "Inconsistent"
        note = f"Inconsistent / Erratic: High daily return deviation ({std_dev:.2f}%), signaling sharp swings."

    if pct_change <= -5.0:
        return "RISKY", "risky-badge", f"RISKY TIER: Value decreased by {abs(pct_change):.2f}% (5%+ drop threshold triggered).", pct_change, std_dev, cons, note
    elif pct_change > 1.5 and std_dev > 2.5:
        return "RISKY (VOLATILE)", "risky-badge", f"RISKY / INCONSISTENT: Grew {pct_change:+.2f}%, but high deviation ({std_dev:.2f}%) flags erratic swings.", pct_change, std_dev, cons, note
    elif pct_change > 1.5:
        return "TOP STOCK", "top-badge", f"TOP STOCKS TIER: Grew {pct_change:+.2f}% (> +1.5%) with {cons.lower()} stability.", pct_change, std_dev, cons, note
    else:
        return "NEUTRAL", "neutral-badge", f"NEUTRAL TIER: Price changed by {pct_change:+.2f}% (between -5.0% and +1.5%).", pct_change, std_dev, cons, note

st.title("🤖 StocAI")
st.caption("Rule-Based Growth & Standard Deviation Stock Classifier for Indian Markets")

remaining = max(0, FREE_LIMIT - st.session_state.checks_used)
st.info(f"StocAI Free Plan: {remaining} of {FREE_LIMIT} scans remaining today.")

tab1, tab2, tab3 = st.tabs(["Single Stock Analyzer", "Nifty-15 Auto Scanner", "StocAI Pro"])
lookback_map = {"1 Day": 1, "1 Week (5D)": 5, "1 Month (21D)": 21}

with tab1:
    c1, c2, c3 = st.columns(3)
    with c1:
        raw_ticker = st.text_input("Company Name or Ticker:", value="ZOMATO")
    with c2:
        exchange = st.selectbox("Exchange", ["NSE (.NS)", "BSE (.BO)"])
    with c3:
        timeframe = st.selectbox("Timeframe", ["1 Day", "1 Week (5D)", "1 Month (21D)"], index=1)

    lookback_days = lookback_map[timeframe]
    is_nse = "NSE" in exchange

    if st.button("Run StocAI Analysis", use_container_width=True):
        if st.session_state.checks_used >= FREE_LIMIT:
            st.error("You've used all 3 free StocAI scans! Check the StocAI Pro tab for unlimited access.")
        elif not raw_ticker.strip():
            st.warning("Please enter an Indian company name or ticker.")
        else:
            with st.spinner("Analyzing..."):
                try:
                    resolved_ticker, base_symbol = resolve_indian_ticker(raw_ticker, prefer_nse=is_nse)
                    live_data = fetch_live_nse_quote(base_symbol) if resolved_ticker.endswith(".NS") else None
                    hist, short_name = fetch_stock_history(resolved_ticker)

                    if hist.empty or len(hist) < 2:
                        st.error("Could not find stock data. Verify the spelling and try again.")
                    else:
                        st.session_state.checks_used += 1
                        if live_data:
                            live_price = live_data["live_price"]
                            live_day_pct = live_data["day_change_pct"]
                            company_name = live_data["company_name"]
                            data_source = live_data["source"]
                        else:
                            live_price = float(hist["Close"].iloc[-1])
                            prev_close = float(hist["Close"].iloc[-2])
                            live_day_pct = ((live_price - prev_close) / prev_close) * 100
                            company_name = short_name
                            data_source = "Exchange Market Feed (" + resolved_ticker + ")"

                        tier, badge, summary, pct_chg, std_d, cons, note = classify_stock(live_price, hist, lookback_days, live_day_pct)
                        st.divider()
                        st.subheader(f"{company_name} ({resolved_ticker})")
                        st.caption(f"Data Source: {data_source}")
                        st.markdown(f'<div class="{badge}">{summary}</div>', unsafe_allow_html=True)

                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Price", f"₹{live_price:,.2f}")
                        m2.metric(f"{timeframe} Growth", f"{pct_chg:+.2f}%", f"{pct_chg:+.2f}%")
                        m3.metric("Daily Deviation", f"{std_d:.2f}%")
                        m4.metric("Stability", cons)

                        st.markdown("### Consistency & Deviation Check")
                        st.write(note)
                        st.markdown("### 3-Month Price Trend")
                        st.line_chart(hist["Close"])
                except Exception as e:
                    st.error(f"Error: {e}")

with tab2:
    st.subheader("One-Click Nifty-15 Market Scanner")
    scan_tf = st.selectbox("Scanner Timeframe", ["1 Day", "1 Week (5D)", "1 Month (21D)"], index=1, key="batch_tf")
    batch_days = lookback_map[scan_tf]
    nifty_sample = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "LT.NS", "ITC.NS", "HINDUNILVR.NS", "ETERNAL.NS", "SUNPHARMA.NS", "MARUTI.NS", "TITAN.NS", "BAJFINANCE.NS"]