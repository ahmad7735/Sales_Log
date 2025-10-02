import os
import streamlit as st
from sqlalchemy import create_engine, text

# (Optional) last-resort fallback so your app still runs even if no secret/env is set.
# Best practice is to use Streamlit secrets or an env var instead of hardcoding.
DEFAULT_DB_URL = "postgresql://neondb_owner:npg_Abuy5pmRZjY7@ep-cool-paper-adc0assr-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_engine():
    # 1) Try Streamlit secrets first
    url = None
    try:
        url = st.secrets["database"]["url"]
    except Exception:
        pass

    # 2) Fallback to environment variable named DATABASE_URL
    if not url:
        url = os.getenv("DATABASE_URL")

    # 3) Last resort: use the inline fallback (not recommended for production)
    if not url:
        url = DEFAULT_DB_URL

    # Optional: ensure SQLAlchemy driver prefix
    if url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return create_engine(url, pool_pre_ping=True)

def init_schema():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS saleslog (
            QuoteID      INTEGER PRIMARY KEY,
            Client       TEXT,
            QuotedPrice  DOUBLE PRECISION DEFAULT 0,
            Status       TEXT,
            SalesRep     TEXT,
            "Deposit%"   DOUBLE PRECISION DEFAULT 0,
            DepositPaid  DOUBLE PRECISION DEFAULT 0,
            SentDate     DATE,
            JobType      TEXT
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS collections (
            id             BIGSERIAL PRIMARY KEY,
            QuoteID        INTEGER REFERENCES saleslog(QuoteID) ON DELETE CASCADE,
            CollectionDate DATE,
            Client         TEXT,
            DepositPaid    DOUBLE PRECISION DEFAULT 0,
            BalanceDue     DOUBLE PRECISION DEFAULT 0,
            Status         TEXT
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS assignments (
            id         BIGSERIAL PRIMARY KEY,
            QuoteID    INTEGER REFERENCES saleslog(QuoteID) ON DELETE CASCADE,
            Client     TEXT,
            CrewMember TEXT,
            StartDate  DATE,
            EndDate    DATE,
            Payment    DOUBLE PRECISION DEFAULT 0,
            DaysTaken  INTEGER DEFAULT 0,
            Notes      TEXT,
            Completed  BOOLEAN DEFAULT FALSE,
            TaskStatus TEXT
        );
        """))
