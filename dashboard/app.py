"""Streamlit dashboard for Store Intelligence API."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

DEFAULT_API = os.getenv("STORE_API_URL", "http://localhost:8000")
DEFAULT_STORE = os.getenv("STORE_ID", "STORE_BLR_002")


def fetch_json(client: httpx.Client, path: str) -> dict | list:
    response = client.get(path, timeout=30.0)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=10)
def load_store_data(api_base: str, store_id: str) -> dict:
    base = api_base.rstrip("/")
    with httpx.Client() as client:
        return {
            "health": fetch_json(client, f"{base}/health"),
            "metrics": fetch_json(client, f"{base}/stores/{store_id}/metrics"),
            "funnel": fetch_json(client, f"{base}/stores/{store_id}/funnel"),
            "heatmap": fetch_json(client, f"{base}/stores/{store_id}/heatmap"),
            "anomalies": fetch_json(client, f"{base}/stores/{store_id}/anomalies"),
        }


def main() -> None:
    st.set_page_config(
        page_title="Store Intelligence",
        page_icon="📊",
        layout="wide",
    )

    st.title("Store Intelligence Dashboard")
    st.caption("Real-time retail analytics from CCTV behavioural events")

    with st.sidebar:
        st.header("Settings")
        api_base = st.text_input("API URL", value=DEFAULT_API)
        store_id = st.text_input("Store ID", value=DEFAULT_STORE)
        refresh = st.button("Refresh data", type="primary")
        st.divider()
        st.markdown(
            "**Prerequisites**\n\n"
            "1. Start API: `uvicorn app.main:app --reload --port 8000`\n\n"
            "2. Ingest events: `python scripts/ingest_events.py`\n\n"
            "3. Set `METRICS_REFERENCE_DATE=2026-03-03T12:00:00Z` on API"
        )

    if refresh:
        load_store_data.clear()

    try:
        data = load_store_data(api_base, store_id)
    except httpx.ConnectError:
        st.error(
            "Cannot connect to the API. Start the server first:\n\n"
            "`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`"
        )
        st.stop()
    except httpx.HTTPStatusError as exc:
        st.error(f"API error: {exc.response.status_code} — {exc.response.text}")
        st.stop()
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
        st.stop()

    health = data["health"]
    metrics = data["metrics"]
    funnel = data["funnel"]
    heatmap = data["heatmap"]
    anomalies = data["anomalies"]

    status_col, db_col, feed_col, rev_col = st.columns(4)
    status_col.metric("Service status", health.get("status", "—").upper())
    db_col.metric("Database", health.get("database", "—"))
    feed_col.metric("Unique visitors", metrics.get("unique_visitors", 0))
    rev_col.metric("Revenue (INR)", f"{metrics.get('total_revenue_inr', 0):,.0f}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Conversion rate", f"{metrics.get('conversion_rate', 0) * 100:.1f}%")
    m2.metric("Queue depth", metrics.get("queue_depth", 0))
    m3.metric("Abandonment rate", f"{metrics.get('abandonment_rate', 0) * 100:.1f}%")
    m4.metric(
        "Analysis window",
        f"{metrics.get('window_start', '')[:10]}",
        help=f"{metrics.get('window_start')} → {metrics.get('window_end')}",
    )

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Conversion funnel")
        stages = funnel.get("stages", [])
        if stages:
            funnel_df = pd.DataFrame(stages)
            fig_funnel = px.funnel(
                funnel_df,
                x="count",
                y="stage",
                title=f"Funnel — {store_id}",
            )
            fig_funnel.update_layout(height=400)
            st.plotly_chart(fig_funnel, use_container_width=True)
            st.dataframe(funnel_df, use_container_width=True, hide_index=True)
        else:
            st.info("No funnel data yet. Ingest events first.")

    with right:
        st.subheader("Zone heatmap")
        cells = heatmap.get("cells", [])
        confidence = heatmap.get("data_confidence", "low")
        st.caption(f"Data confidence: **{confidence}**")
        if cells:
            heat_df = pd.DataFrame(cells)
            fig_heat = px.bar(
                heat_df,
                x="zone_id",
                y="score",
                color="visit_frequency",
                labels={"score": "Heat score (0–100)", "zone_id": "Zone"},
                title="Zone visit intensity",
                text="visit_frequency",
            )
            fig_heat.update_layout(height=400)
            st.plotly_chart(fig_heat, use_container_width=True)
            st.dataframe(heat_df, use_container_width=True, hide_index=True)
        else:
            st.info("No zone visits recorded.")

    st.divider()
    st.subheader("Zone dwell times")
    dwell_zones = metrics.get("avg_dwell_by_zone", [])
    if dwell_zones:
        dwell_df = pd.DataFrame(dwell_zones)
        dwell_df["avg_dwell_sec"] = dwell_df["avg_dwell_ms"] / 1000
        fig_dwell = px.bar(
            dwell_df,
            x="zone_id",
            y="avg_dwell_sec",
            title="Average dwell per zone (seconds)",
        )
        st.plotly_chart(fig_dwell, use_container_width=True)
    else:
        st.info("No dwell metrics available.")

    st.divider()
    st.subheader("Active anomalies")
    anomaly_rows = anomalies.get("anomalies", [])
    if anomaly_rows:
        anomaly_df = pd.DataFrame(anomaly_rows)
        display_cols = ["anomaly_type", "severity", "message", "suggested_action"]
        st.dataframe(anomaly_df[display_cols], use_container_width=True, hide_index=True)
    else:
        st.success("No anomalies detected.")

    with st.expander("API health details"):
        st.json(health)


if __name__ == "__main__":
    main()
