import streamlit as st
import pandas as pd
from pykrx import stock
from datetime import datetime, timedelta

# -----------------------------------------------------------------------------
# 분석 로직 (기존 analyzer.py 내용 통합)
# -----------------------------------------------------------------------------

def get_target_days(reference_date_str, duration):
    """
    기준 날짜(reference_date_str) 이전의 영업일 'duration'개를 가져옵니다.
    """
    end_dt = datetime.strptime(reference_date_str, "%Y%m%d")
    start_dt = end_dt - timedelta(days=30)
    
    try:
        # 삼성전자(005930)를 기준으로 영업일 조회
        df = stock.get_market_ohlcv_by_date(start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"), "005930")
        business_days = df.index.strftime("%Y%m%d").tolist()
        
        # 기준 날짜 '미만'의 날짜만 필터링 (기준 날짜 제외)
        valid_days = [d for d in business_days if d < reference_date_str]
        
        if len(valid_days) < duration:
            return []
            
        return valid_days[-duration:]
    except Exception as e:
        print(f"영업일 조회 실패: {e}")
        return []

def get_top_tickers(market, date):
    """
    해당 날짜의 시가총액 상위 100개 종목 티커를 반환합니다.
    """
    try:
        df = stock.get_market_cap(date, market=market)
        return df.sort_values(by="시가총액", ascending=False).head(100).index.tolist()
    except Exception as e:
        print(f"Top 100 조회 실패: {e}")
        return []

def fetch_investor_data(market, investor_code, days):
    """
    특정 투자자의 일별 순매수 데이터를 미리 수집합니다.
    """
    data_map = {} # {date: dataframe}
    for d in days:
        try:
            df = stock.get_market_net_purchases_of_equities_by_ticker(d, d, market, investor_code)
            data_map[d] = df
        except Exception as e:
            print(f"{d} 데이터 수집 실패: {e}")
    return data_map

def run_analysis(market, reference_date_str, duration, threshold_major, threshold_minor):
    """
    분석을 수행하고 결과를 딕셔너리 형태로 반환합니다.
    """
    # 1. 분석 대상 날짜 확보
    days = get_target_days(reference_date_str, duration)
    if not days:
        return {"error": f"유효한 영업일 {duration}일을 확보하지 못했습니다. (기준일: {reference_date_str})"}
    
    last_day = days[-1]
    
    # 2. 시가총액 Top 100 선정
    top100 = get_top_tickers(market, last_day)
    if not top100:
        return {"error": "시가총액 상위 종목을 가져오는데 실패했습니다."}
    
    # 3. 투자자 정의
    investors = [
        {"code": "외국인", "name": "외국인", "threshold": threshold_major},
        {"code": "기관합계", "name": "기관", "threshold": threshold_major},
        {"code": "연기금", "name": "연기금", "threshold": threshold_minor},
    ]
    
    results = {} # {investor_name: [ {ticker, name, total, amounts} ]}
    ticker_info = {} # {ticker: name}
    
    # 교집합 분석을 위한 맵
    ticker_investor_map = {} # {ticker: {investor_name: amount}}
    
    for inv in investors:
        inv_name = inv["name"]
        inv_code = inv["code"]
        threshold = inv["threshold"]
        
        # 해당 투자자의 일별 데이터 수집
        daily_data = fetch_investor_data(market, inv_code, days)
        
        inv_results = []
        
        for ticker in top100:
            is_consecutive = True
            amounts = []
            
            for d in days:
                # 데이터가 없거나 해당 종목이 없으면 탈락
                if d not in daily_data or ticker not in daily_data[d].index:
                    is_consecutive = False
                    break
                
                # 순매수 확인
                if '순매수거래대금' in daily_data[d].columns:
                    val = daily_data[d].loc[ticker, "순매수거래대금"]
                    if val <= 0:
                        is_consecutive = False
                        break
                    amounts.append(val)
                else:
                    is_consecutive = False
                    break
            
            if is_consecutive:
                total = sum(amounts)
                if total > threshold:
                    name = stock.get_market_ticker_name(ticker)
                    ticker_info[ticker] = name
                    
                    row = {
                        "ticker": ticker,
                        "name": name,
                        "total": total,
                        "amounts": amounts
                    }
                    inv_results.append(row)
                    
                    # 교집합 맵에 추가
                    if ticker not in ticker_investor_map:
                        ticker_investor_map[ticker] = {}
                    ticker_investor_map[ticker][inv_name] = total

        # 총합 기준 내림차순 정렬
        inv_results.sort(key=lambda x: x["total"], reverse=True)
        results[inv_name] = inv_results

    # 4. 교집합(2개 이상 주체) 분석
    intersection_results = []
    for ticker, inv_map in ticker_investor_map.items():
        if len(inv_map) >= 2:
            total_sum = sum(inv_map.values())
            involved = list(inv_map.keys())
            intersection_results.append({
                "ticker": ticker,
                "name": ticker_info[ticker],
                "total": total_sum,
                "involved": involved
            })
    
    # 교집합 결과 정렬
    intersection_results.sort(key=lambda x: x["total"], reverse=True)
    
    return {
        "days": days,
        "individual": results,
        "intersection": intersection_results
    }

# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------

# 페이지 설정
st.set_page_config(page_title="수급 분석기", layout="wide")

# 사이드바 설정
st.sidebar.title("🔍 수급 분석기")

market = st.sidebar.radio("시장 선택", ["KOSPI", "KOSDAQ"])
ref_date = st.sidebar.date_input("기준 날짜", datetime.now())
duration = st.sidebar.slider("연속 순매수 기간 (일)", 2, 5, 3)

st.sidebar.subheader("금액 기준 (단위: 억원)")
th_major = st.sidebar.number_input("메이저 (외국인/기관)", value=100)
th_minor = st.sidebar.number_input("마이너 (연기금)", value=10)

if st.sidebar.button("분석 시작", type="primary"):
    with st.spinner("데이터를 분석하고 있습니다... (약 10~20초 소요)"):
        # 날짜 변환
        ref_date_str = ref_date.strftime("%Y%m%d")
        
        # 금액 단위 변환 (억원 -> 원)
        threshold_major = th_major * 100000000
        threshold_minor = th_minor * 100000000
        
        # 분석 실행 (내부 함수 호출)
        data = run_analysis(market, ref_date_str, duration, threshold_major, threshold_minor)
        
        if "error" in data:
            st.error(data["error"])
        else:
            days = data["days"]
            # 날짜 포맷팅 (YYYYMMDD -> MM/DD)
            formatted_days = [f"{d[4:6]}/{d[6:]}" for d in days]
            days_range_str = f"{formatted_days[0]} ~ {formatted_days[-1]}"
            
            st.success(f"📅 분석 기간: {days_range_str} ({len(days)}일간)")
            
            # 탭 구성
            tab1, tab2, tab3, tab4 = st.tabs(["🏆 베스트 (교집합)", "👽 외국인", "🏢 기관", "💰 연기금"])
            
            def make_df(result_list, is_intersection=False):
                if not result_list:
                    return pd.DataFrame()
                
                rows = []
                for item in result_list:
                    row = {
                        "종목명": f"{item['name']}({item['ticker']})",
                        "총합(억원)": round(item['total'] / 100000000, 1)
                    }
                    if is_intersection:
                        row["포함 주체"] = ", ".join(item['involved'])
                    else:
                        # 일별 데이터 추가
                        for i, d in enumerate(formatted_days):
                            row[d] = round(item['amounts'][i] / 100000000, 1)
                    rows.append(row)
                return pd.DataFrame(rows)

            with tab1:
                st.markdown("##### 2개 이상 주체가 동시에 순매수한 종목 (합산 금액순)")
                df = make_df(data["intersection"], is_intersection=True)
                if df.empty:
                    st.info("조건에 맞는 종목이 없습니다.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)
            
            with tab2:
                st.markdown(f"##### 외국인 {duration}일 연속 순매수 (총합 {th_major}억 이상)")
                df = make_df(data["individual"]["외국인"])
                if df.empty:
                    st.info("조건에 맞는 종목이 없습니다.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)

            with tab3:
                st.markdown(f"##### 기관 {duration}일 연속 순매수 (총합 {th_major}억 이상)")
                df = make_df(data["individual"]["기관"])
                if df.empty:
                    st.info("조건에 맞는 종목이 없습니다.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)

            with tab4:
                st.markdown(f"##### 연기금 {duration}일 연속 순매수 (총합 {th_minor}억 이상)")
                df = make_df(data["individual"]["연기금"])
                if df.empty:
                    st.info("조건에 맞는 종목이 없습니다.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)
