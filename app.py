import streamlit as st
import pandas as pd
from datetime import datetime
import analyzer

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
        
        # 분석 실행
        data = analyzer.run_analysis(market, ref_date_str, duration, threshold_major, threshold_minor)
        
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
