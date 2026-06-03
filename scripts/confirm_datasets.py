from dotenv import load_dotenv
import os, requests, pandas as pd
from datetime import datetime, timedelta

load_dotenv()
TOKEN = os.environ["FINMIND_TOKEN"]
URL = "https://api.finmindtrade.com/api/v4/data"
TEST_IDS = ["2330", "2308", "4958", "6669", "2454"]

def fetch(dataset, stock_id, days_back=60):
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    r = requests.get(URL, params={"dataset": dataset, "data_id": stock_id, "start_date": start, "token": TOKEN}, timeout=20)
    return r.json().get("data", [])

print("=" * 55)
print("CONFIRM-1: TaiwanStockInstitutionalInvestorsBuySell")
print("=" * 55)
s = fetch("TaiwanStockInstitutionalInvestorsBuySell", "2330", 35)
if s:
    print("  columns:", list(s[0].keys()))
    names = sorted({d["name"] for d in s})
    print("  name values:", names)
    df = pd.DataFrame(s)
    df["net"] = pd.to_numeric(df["buy"]) - pd.to_numeric(df["sell"])
    ld = df["date"].max()
    net = df[df["date"]==ld]["net"].sum()
    print(f"  latest date: {ld}, net_buy_all: {net:,.0f}")
else:
    print("  EMPTY")

print()
avail = 0
for sid in TEST_IDS:
    d = fetch("TaiwanStockInstitutionalInvestorsBuySell", sid, 20)
    st = f"OK {len(d)} rows" if d else "EMPTY"
    if d: avail += 1
    print(f"  {sid}: {st}")
print(f"  coverage: {avail}/{len(TEST_IDS)}")

print()
print("=" * 55)
print("CONFIRM-2: TaiwanStockMonthRevenue")
print("=" * 55)
s2 = fetch("TaiwanStockMonthRevenue", "2330", 400)
if s2:
    print("  columns:", list(s2[0].keys()))
    print("  last 2:", s2[-2:])
    df2 = pd.DataFrame(s2)
    rev_col = "revenue" if "revenue" in df2.columns else df2.columns[-1]
    print(f"  revenue column used: {rev_col}")
    df2[rev_col] = pd.to_numeric(df2[rev_col], errors="coerce")
    df2["date"] = pd.to_datetime(df2["date"])
    df2 = df2.sort_values("date").reset_index(drop=True)
    if len(df2) >= 13:
        r_now = df2.iloc[-1][rev_col]
        r_yoy = df2.iloc[-13][rev_col]
        yoy = (r_now/r_yoy - 1)*100 if r_yoy else None
        d_now = df2.iloc[-1]["date"].strftime("%Y-%m")
        d_yoy = df2.iloc[-13]["date"].strftime("%Y-%m")
        print(f"  YoY {d_now} vs {d_yoy}: {yoy:.1f}%" if yoy else "  YoY: N/A")
else:
    print("  EMPTY")

print()
avail2 = 0
for sid in TEST_IDS:
    d = fetch("TaiwanStockMonthRevenue", sid, 400)
    if d:
        avail2 += 1
        st = f"OK {len(d)} months, latest={d[-1].get('date','?')}"
    else:
        st = "EMPTY"
    print(f"  {sid}: {st}")
print(f"  coverage: {avail2}/{len(TEST_IDS)}")

print()
print("=" * 55)
print("CONFIRM-3: sheet.py Signals columns")
print("=" * 55)
import re
with open("stock_strategies/sheet.py", encoding="utf-8") as f:
    content = f.read()
match = re.search(r"ws\.append_row\(\[(.*?)\]\)", content, re.DOTALL)
if match:
    raw = match.group(1)
    cols = [c.strip().strip('"').strip("'") for c in raw.split(",") if c.strip()]
    print(f"  total columns: {len(cols)}")
    for i, c in enumerate(cols, 1):
        print(f"  {i:2d}. {c}")
print()
print("DONE")
