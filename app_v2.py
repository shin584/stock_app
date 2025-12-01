import streamlit as st
import pandas as pd
from pykrx import stock
from datetime import datetime, timedelta
import time

# -----------------------------------------------------------------------------
# 데이터 수집 및 분석 함수
# -----------------------------------------------------------------------------

@st.cache_data(ttl=3600) # 1시간 캐싱
def get_market_data(date_str, market):
    """
    해당 날짜의 시세, 시가총액, 투자자별 순매수, 프로그램 매매 데이터를 모두 가져옵니다.
    """
    # 1. 기본 시세 및 시가총액 (등락률, 시총 확인용)
    try:
        df_cap = stock.get_market_cap(date_str, market=market)
        df_ohlcv = stock.get_market_ohlcv(date_str, market=market)
        # 등락률 컬럼 병합
        df_master = df_cap.join(df_ohlcv['등락률'])
    except Exception as e:
        return None, f"시세 데이터 조회 실패: {e}"

    # 2. 투자자별 순매수 (외국인, 금융투자, 투신, 연기금)
    investors = ['외국인', '금융투자', '투신', '연기금']
    for inv in investors:
        col_name = f'{inv}_순매수'
        try:
            df = stock.get_market_net_purchases_of_equities_by_ticker(date_str, date_str, market, inv)
            # 컬럼명 변경: 순매수거래대금 -> 외국인_순매수, 등
            df = df[['순매수거래대금']].rename(columns={'순매수거래대금': col_name})
            df_master = df_master.join(df, how='left')
        except:
            pass # 데이터 없으면 패스 (NaN 처리됨)
        
        # 데이터 수집 실패 시 해당 컬럼을 0으로 채움 (KeyError 방지)
        if col_name not in df_master.columns:
            df_master[col_name] = 0

    # 3. 프로그램 매매 (순매수)
    try:
        # pykrx의 프로그램 매매 조회 기능 활용 (종목별)
        df_prog = stock.get_market_program_net_purchases_of_equities_by_ticker(date_str, date_str, market)
        df_prog = df_prog[['순매수거래대금']].rename(columns={'순매수거래대금': '프로그램_순매수'})
        df_master = df_master.join(df_prog, how='left')
    except:
        # 프로그램 매매 데이터 조회 실패 시 0으로 처리 (Priority 1 조건 체크 불가)
        df_master['프로그램_순매수'] = 0

    return df_master.fillna(0), None

def get_recent_business_days(ref_date_str, duration=3):
    """
    기준일 포함 최근 N일의 영업일 리스트 반환
    """
    try:
        end_dt = datetime.strptime(ref_date_str, "%Y%m%d")
        start_dt = end_dt - timedelta(days=20)
        df_days = stock.get_market_ohlcv_by_date(start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"), "005930")
        return df_days.index[-duration:].strftime("%Y%m%d").tolist()
    except:
        return []

def get_foreign_ownership_change(market, current_date_str, days_ago=30):
    """
    최근 30일간 외국인 지분율 변동폭 계산
    """
    try:
        # 현재 지분율
        df_curr = stock.get_exhaustion_rates_of_foreign_investment_by_ticker(current_date_str, market)
        df_curr = df_curr[['지분율']].rename(columns={'지분율': '지분율_현재'})
        
        # 30일 전 영업일 찾기
        curr_dt = datetime.strptime(current_date_str, "%Y%m%d")
        target_dt = curr_dt - timedelta(days=days_ago)
        
        # 넉넉하게 10일 전부터 검색해서 가장 최근 영업일 확보
        search_start = target_dt - timedelta(days=10)
        search_end = target_dt
        
        # 삼성전자 기준으로 영업일 확인
        df_days = stock.get_market_ohlcv_by_date(search_start.strftime("%Y%m%d"), search_end.strftime("%Y%m%d"), "005930")
        
        if df_days.empty:
            return None
            
        prev_date_str = df_days.index[-1].strftime("%Y%m%d")
        
        # 과거 지분율
        df_prev = stock.get_exhaustion_rates_of_foreign_investment_by_ticker(prev_date_str, market)
        df_prev = df_prev[['지분율']].rename(columns={'지분율': '지분율_과거'})
        
        # 병합 및 변동폭 계산
        df_merge = df_curr.join(df_prev, how='left')
        df_merge['지분변동'] = df_merge['지분율_현재'] - df_merge['지분율_과거']
        
        return df_merge[['지분변동']]
    except Exception as e:
        print(f"지분율 분석 실패: {e}")
        return None

def get_consecutive_tickers_sets(market, valid_days):
    """
    반환값: (strict_set, relaxed_set, for_consecutive, trust_consecutive, pension_consecutive)
    """
    try:
        if not valid_days:
            return set(), set(), set(), set(), set()
            
        # 2. 일별 데이터 수집 및 교집합 연산
        for_consecutive = None
        trust_consecutive = None
        pension_consecutive = None
        
        for d in valid_days:
            # 외국인
            df_for = stock.get_market_net_purchases_of_equities_by_ticker(d, d, market, "외국인")
            buy_for = set(df_for[df_for['순매수거래대금'] > 0].index)
            if for_consecutive is None:
                for_consecutive = buy_for
            else:
                for_consecutive.intersection_update(buy_for)
                
            # 투신
            df_trust = stock.get_market_net_purchases_of_equities_by_ticker(d, d, market, "투신")
            buy_trust = set(df_trust[df_trust['순매수거래대금'] > 0].index)
            if trust_consecutive is None:
                trust_consecutive = buy_trust
            else:
                trust_consecutive.intersection_update(buy_trust)

            # 연기금
            df_pension = stock.get_market_net_purchases_of_equities_by_ticker(d, d, market, "연기금")
            buy_pension = set(df_pension[df_pension['순매수거래대금'] > 0].index)
            if pension_consecutive is None:
                pension_consecutive = buy_pension
            else:
                pension_consecutive.intersection_update(buy_pension)
                
        if for_consecutive is None: for_consecutive = set()
        if trust_consecutive is None: trust_consecutive = set()
        if pension_consecutive is None: pension_consecutive = set()
        
        # Strict: 3개 모두 교집합
        strict_set = for_consecutive.intersection(trust_consecutive).intersection(pension_consecutive)
        
        # Relaxed: 2개 이상 교집합 ((A&B) | (B&C) | (A&C))
        relaxed_set = (for_consecutive & trust_consecutive) | \
                      (trust_consecutive & pension_consecutive) | \
                      (for_consecutive & pension_consecutive)
        
        return strict_set, relaxed_set, for_consecutive, trust_consecutive, pension_consecutive
    except Exception as e:
        print(f"연속 순매수 조회 실패: {e}")
        return set(), set(), set(), set(), set()

def analyze_market_v2(market, date_str):
    # 1. 영업일 확보
    valid_days = get_recent_business_days(date_str, 3)
    if len(valid_days) < 3:
        return {"error": "최근 3일치 영업일을 확보하지 못했습니다."}
    
    # 실제 분석 기준일 (휴장일 선택 시 가장 최근 영업일로 자동 조정됨)
    actual_date_str = valid_days[-1]
        
    # 2. 당일 데이터 수집 (필터링 및 로직용)
    df, error = get_market_data(actual_date_str, market)
    if error:
        return {"error": error}
        
    # 3. 3일 평균 데이터 수집 (표시용)
    start_d, end_d = valid_days[0], valid_days[-1]
    df_avgs = pd.DataFrame()
    investors_for_avg = ['외국인', '금융투자', '투신', '연기금']
    
    # 순매수 평균 계산
    for inv in investors_for_avg:
        try:
            # 기간 합계 조회
            df_tmp = stock.get_market_net_purchases_of_equities_by_ticker(start_d, end_d, market, inv)
            # 3으로 나누어 평균 계산
            df_tmp = df_tmp[['순매수거래대금']] / 3
            df_tmp.columns = [f'{inv}_평균']
            if df_avgs.empty:
                df_avgs = df_tmp
            else:
                df_avgs = df_avgs.join(df_tmp, how='outer')
        except:
            pass
            
    # 등락률 평균 계산
    df_fluc_sum = pd.DataFrame()
    for d in valid_days:
        try:
            df_tmp = stock.get_market_ohlcv(d, market=market)[['등락률']]
            if df_fluc_sum.empty:
                df_fluc_sum = df_tmp
            else:
                df_fluc_sum = df_fluc_sum.add(df_tmp, fill_value=0)
        except:
            pass
            
    if not df_fluc_sum.empty:
        df_fluc_avg = df_fluc_sum / len(valid_days)
        df_fluc_avg.columns = ['평균등락률']
        df_avgs = df_avgs.join(df_fluc_avg, how='outer')
            
    # 당일 데이터와 평균 데이터 병합
    df = df.join(df_avgs, how='left').fillna(0)
    
    # 4. 외국인 지분 변동 (30일)
    df_foreign_change = get_foreign_ownership_change(market, actual_date_str, 30)
    if df_foreign_change is not None:
        df = df.join(df_foreign_change, how='left')
        df['지분변동'] = df['지분변동'].fillna(0)
    else:
        df['지분변동'] = 0
    
    results = []
    
    # 수급비중 상위 50개 종목 선정 (가산점용)
    df['주요수급합계'] = df['외국인_순매수'] + df['투신_순매수'] + df['연기금_순매수']
    df['수급비중'] = df['주요수급합계'] / df['시가총액']
    top_ratio_tickers = df.sort_values(by='수급비중', ascending=False).head(50).index.tolist()
    
    # 3일 연속 순매수 종목 사전 확보 (필터링용)
    strict_set, relaxed_set, set_for, set_trust, set_pension = get_consecutive_tickers_sets(market, valid_days)
    
    total_count = len(df)
    processed_count = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    for ticker, row in df.iterrows():
        processed_count += 1
        if processed_count % 50 == 0:
            progress = processed_count / total_count
            progress_bar.progress(progress)
            status_text.text(f"분석 중... ({processed_count}/{total_count})")

        market_cap = row['시가총액']
        fluctuation = row['등락률']
        
        prog_buy = row['프로그램_순매수']
        for_buy = row['외국인_순매수']
        inv_trust_buy = row['투신_순매수']
        pension_buy = row['연기금_순매수']
        
        # --- [Step 1: 필터링 (광탈 조건)] ---
        
        # 1. 당일 주가상승률 15% 이상 과열 종목 제외
        if fluctuation >= 15.0:
            continue
            
        # 2. 금융투자 대량 매도 제외 (시총의 -0.1% 이상 매도)
        if row['금융투자_순매수'] < -(market_cap * 0.001):
            continue
            
        # 3. 필터링 로직 (1순위 조건 만족 시 연속 순매수 무관하게 통과)
        # 1순위 조건: 프로그램 매도, 외인(20억↑)/투신(10억↑)/연기금(10억↑) 매수
        is_priority_1 = (
            (prog_buy < 0) and 
            (for_buy >= 2000000000) and 
            (inv_trust_buy >= 1000000000) and 
            (pension_buy >= 1000000000)
        )
        
        if not is_priority_1 and (ticker not in relaxed_set):
            continue
            
        is_strict = ticker in strict_set
            
        # --- [Step 2: 점수 산정 (Scoring)] ---
        # 점수 산정은 '당일' 수급 패턴을 기준으로 함 (빈집털이 등은 당일 현상)
        score = 0
        priority_type = "None"
        reasons = []
        
        # Priority 1 (빈집털이형) - No History Required
        if is_priority_1:
            score += 100
            priority_type = "1순위"
            reasons.append("프로그램 매도세 극복")
            
        # Priority 2 (정석 주도주형) - Strict History Required
        elif is_strict and (for_buy > 0) and (inv_trust_buy > 0) and (pension_buy > 0):
            score += 70
            priority_type = "2순위"
            reasons.append("외인/투신/연기금 동반 매수")
            
        # Priority 3 (차선책) - Relaxed History OK
        else:
            buy_count = 0
            if for_buy > 0: buy_count += 1
            if inv_trust_buy > 0: buy_count += 1
            if pension_buy > 0: buy_count += 1
            
            if buy_count >= 2:
                # 3순위 추가 필터: 연속 순매수 주체별 금액 조건 체크
                # 외국인: 20억 이상, 투신/연기금: 10억 이상 (3일 평균)
                pass_filter = True
                
                # 연속 순매수한 주체 확인
                consecutive_entities = []
                if ticker in set_for: consecutive_entities.append('외국인')
                if ticker in set_trust: consecutive_entities.append('투신')
                if ticker in set_pension: consecutive_entities.append('연기금')
                
                for entity in consecutive_entities:
                    avg_amt = row[f'{entity}_평균']
                    if entity == '외국인':
                        if avg_amt < 2000000000: # 20억
                            pass_filter = False
                            break
                    elif entity in ['투신', '연기금']:
                        if avg_amt < 1000000000: # 10억
                            pass_filter = False
                            break
                
                if pass_filter:
                    score += 40
                    priority_type = "3순위"
                    reasons.append(f"주요 주체 {buy_count}곳 매수")
        
        # 점수가 없으면 탈락
        if score == 0:
            continue
            
        # 종목명 조회
        name = stock.get_market_ticker_name(ticker)

        # --- [Step 3: 가산점 (Bonus)] ---
        if ticker in top_ratio_tickers:
            score += 10
            reasons.append("수급비중 상위")
            
        # 평균 순매수 합계 계산 (정렬용) - 금융투자 제외
        avg_sum = row['외국인_평균'] + row['투신_평균'] + row['연기금_평균']
        
        # 4. 평균 순매수 합계 10억 미만 제외
        if avg_sum < 1000000000:
            continue

        # 5. 각 주체별 3일 평균 순매수 중 하나라도 음수이면 제외
        if (row['외국인_평균'] < 0) or (row['투신_평균'] < 0) or (row['연기금_평균'] < 0):
            continue
            
        # 결과 저장 (금액은 평균값으로 저장)
        results.append({
            'ticker': ticker,
            'name': name,
            'score': score,
            'priority': priority_type,
            'fluctuation': row['평균등락률'],
            'market_cap': market_cap,
            'reasons': ", ".join(reasons),
            'total_avg': avg_sum,
            'amounts': {
                '외국인': row['외국인_평균'],
                '투신': row['투신_평균'],
                '연기금': row['연기금_평균'],
                '금융투자': row['금융투자_평균']
            },
            'is_strict': is_strict,
            'foreign_diff': row['지분변동']
        })
        
    progress_bar.empty()
    status_text.empty()
    
    # 정렬: 1. 순위(오름차순), 2. 점수(내림차순), 3. 합계(내림차순)
    results.sort(key=lambda x: (x['priority'], -x['score'], -x['total_avg']))
    
    return {"results": results, "actual_date": actual_date_str}

# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------

st.set_page_config(page_title="수급 분석기 V2", layout="wide")

st.title("🎯 수급 분석기 V2 (Scoring Model)")
st.markdown("""
**알고리즘 개요**
*   **1순위 (빈집털이)**: 프로그램 매도 + 외국인(20억↑), 투신(10억↑), 연기금(10억↑) 당일 매수 (+100점)
*   **2순위 (정석 주도주)**: 외국인, 투신, 연기금 모두 3일 연속 매수 (+70점)
*   **3순위 (차선책)**: 3주체 중 2곳 이상 3일 연속 매수 (+40점)
*   **필터링**: 주가 급등(>15%) 제외, 금융투자 대량 매도 제외, 3일 평균 순매수 합계 10억(3순위의 경우 주체별 3일 평균 금액 조건 추가)
*   **가산점**: 수급비중 상위 50종목 (+10점)
""")

col1, col2, col3 = st.columns(3)
with col1:
    market = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True)
with col2:
    # 기본값을 어제 날짜로 설정
    default_date = datetime.now() - timedelta(days=1)
    ref_date = st.date_input("분석 기준일", default_date)
with col3:
    st.write("") # Spacer
    run_btn = st.button("분석 시작", type="primary", use_container_width=True)

if run_btn:
    date_str = ref_date.strftime("%Y%m%d")
    
    with st.spinner("데이터 수집 및 분석 중입니다... (약 30초 소요)"):
        data = analyze_market_v2(market, date_str)
        
        if "error" in data:
            st.error(data["error"])
        else:
            results = data["results"]
            actual_date = data.get("actual_date", date_str)
            
            if actual_date != date_str:
                st.warning(f"선택하신 날짜는 휴장일이거나 데이터가 없어, 가장 최근 영업일인 {actual_date} 기준으로 분석했습니다.")
            
            st.success(f"분석 완료! 총 {len(results)}개 종목이 포착되었습니다.")
            
            if not results:
                st.info("조건을 만족하는 종목이 없습니다.")
            else:
                # 데이터프레임 변환
                rows = []
                for r in results:
                    amt = r['amounts']
                    rows.append({
                        "순위": r['priority'],
                        "점수": r['score'],
                        "종목명": r['name'][:4],
                        "등락률": f"{r['fluctuation']:.2f}%",
                        "특이사항": r['reasons'],
                        "합계": round(r['total_avg'] / 100000000, 1),
                        "외국인": round(amt['외국인'] / 100000000, 1),
                        "투신": round(amt['투신'] / 100000000, 1),
                        "연기금": round(amt['연기금'] / 100000000, 1),
                        "외인지분변동": f"{r['foreign_diff']:.2f}%p" if r['foreign_diff'] > 0 else f"{r['foreign_diff']:.2f}%p",
                    })
                
                df_res = pd.DataFrame(rows)
                
                # 스타일링
                st.dataframe(
                    df_res,
                    column_config={
                        "점수": st.column_config.NumberColumn(
                            "점수",
                            format="%d",
                        ),
                        "합계": st.column_config.NumberColumn("합계(억)"),
                        "외국인": st.column_config.NumberColumn("외국인(억)"),
                        "투신": st.column_config.NumberColumn("투신(억)"),
                        "연기금": st.column_config.NumberColumn("연기금(억)"),
                        "외인지분변동": st.column_config.TextColumn("외인지분변동(30일)"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
