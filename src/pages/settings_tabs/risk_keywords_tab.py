"""
Settings Tab: Risk Keyword Management (風險關鍵字管理)
Provides CRUD UI and review/analytics for Sentinel risk keywords.
"""
import logging
from src.data.risk_keyword_repository import RiskKeywordRepository

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "legal": "⚖️ 法律 (Legal)",
    "financial": "💰 財務 (Financial)",
    "operational": "🏭 營運 (Operational)",
    "geopolitical": "🌍 地緣政治 (Geopolitical)",
    "market": "📉 市場 (Market)",
    "custom": "🏷️ 自訂 (Custom)",
}


def render_risk_keywords_tab(st, db_path=None):
    """
    Render the Risk Keywords management tab.
    渲染風險關鍵字管理分頁。
    """
    repo = RiskKeywordRepository(db_path)
    
    # Ensure seed data exists
    repo.seed_defaults()

    st.subheader("🔑 風險關鍵字管理 (Risk Keyword Management)")
    st.caption("管理 Sentinel 哨兵服務用於偵測突發新聞的風險關鍵字。每個關鍵字有權重 (0-1)，越高代表越緊急。")

    # ── Section 1: Add New Keyword ──
    with st.expander("➕ 新增關鍵字 (Add Keyword)", expanded=False):
        col1, col2, col3 = st.columns([3, 2, 2])
        with col1:
            new_keyword = st.text_input("關鍵字 (Keyword)", key="rk_new_keyword")
        with col2:
            new_weight = st.slider("權重 (Weight)", 0.0, 1.0, 0.5, 0.05, key="rk_new_weight")
        with col3:
            new_category = st.selectbox(
                "類別 (Category)",
                options=list(CATEGORY_LABELS.keys()),
                format_func=lambda x: CATEGORY_LABELS.get(x, x),
                key="rk_new_cat"
            )
        if st.button("新增 (Add)", key="rk_add_btn"):
            if new_keyword.strip():
                repo.add(new_keyword.strip(), new_weight, new_category)
                st.success(f"✅ 已新增: {new_keyword} (weight={new_weight})")
                st.rerun()
            else:
                st.warning("請輸入關鍵字")

    # ── Section 2: Keyword List ──
    st.markdown("---")
    
    # Filter controls
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        show_inactive = st.checkbox("顯示已停用 (Show Inactive)", value=False, key="rk_show_inactive")
    with filter_col2:
        filter_category = st.selectbox(
            "篩選類別",
            options=["all"] + list(CATEGORY_LABELS.keys()),
            format_func=lambda x: "全部 (All)" if x == "all" else CATEGORY_LABELS.get(x, x),
            key="rk_filter_cat"
        )

    # Fetch keywords
    if filter_category == "all":
        keywords = repo.get_all(active_only=not show_inactive)
    else:
        keywords = repo.get_by_category(filter_category)
        if not show_inactive:
            keywords = [kw for kw in keywords if kw.is_active]

    if not keywords:
        st.info("無關鍵字 (No keywords found)")
        return

    st.markdown(f"**共 {len(keywords)} 個關鍵字**")

    # Display as editable table
    for idx, kw in enumerate(keywords):
        cat_label = CATEGORY_LABELS.get(kw.category.value, kw.category.value)
        status_emoji = "🟢" if kw.is_active else "🔴"
        
        col_kw, col_w, col_cat, col_hits, col_actions = st.columns([3, 1.5, 2, 1.5, 2])
        
        with col_kw:
            st.text(f"{status_emoji} {kw.keyword}")
        with col_w:
            new_w = st.number_input(
                "W", value=kw.weight, min_value=0.0, max_value=1.0, step=0.05,
                key=f"rk_w_{kw.id}", label_visibility="collapsed"
            )
            if new_w != kw.weight:
                repo.update_weight(kw.id, new_w)
        with col_cat:
            st.caption(cat_label)
        with col_hits:
            hit_text = f"📊 {kw.hit_count}"
            if kw.last_hit_date:
                hit_text += f"\n({kw.last_hit_date})"
            st.caption(hit_text)
        with col_actions:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if kw.is_active:
                    if st.button("⏸️", key=f"rk_pause_{kw.id}", help="停用"):
                        repo.toggle_active(kw.id, False)
                        st.rerun()
                else:
                    if st.button("▶️", key=f"rk_resume_{kw.id}", help="啟用"):
                        repo.toggle_active(kw.id, True)
                        st.rerun()
            with btn_col2:
                if st.button("🗑️", key=f"rk_del_{kw.id}", help="刪除"):
                    repo.delete(kw.id)
                    st.rerun()

    # ── Section 3: Review / Analytics (復盤) ──
    st.markdown("---")
    st.subheader("📊 復盤分析 (Review & Analytics)")
    
    review_col1, review_col2 = st.columns(2)
    
    with review_col1:
        st.markdown("**🏆 命中最多 Top 10 (Most Triggered)**")
        top = repo.get_top_keywords(10)
        if top:
            for kw in top:
                if kw.hit_count > 0:
                    st.text(f"  {kw.keyword}: {kw.hit_count} hits (w={kw.weight:.2f})")
        else:
            st.caption("暫無命中紀錄")
    
    with review_col2:
        st.markdown("**🧊 90 天未觸發 (Stale - Candidates for Removal)**")
        stale = repo.get_stale_keywords(days_threshold=90)
        if stale:
            for kw in stale:
                last = kw.last_hit_date or "Never"
                st.text(f"  {kw.keyword}: last={last} (w={kw.weight:.2f})")
            if st.button("⏸️ 批次停用全部 (Disable All Stale)", key="rk_disable_stale"):
                for kw in stale:
                    repo.toggle_active(kw.id, False)
                st.success(f"已停用 {len(stale)} 個關鍵字")
                st.rerun()
        else:
            st.caption("所有關鍵字都有近期命中")
